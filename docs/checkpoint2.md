# Checkpoint 2 — Không để lộ dữ liệu hoặc tự làm action nguy hiểm

## 1. Phân tích yêu cầu

Input guardrail có thể bỏ sót, vì vậy không được xem nó là lớp bảo vệ duy nhất.
Checkpoint này đặt hai ranh giới độc lập ở cuối luồng:

1. **Output boundary:** redact secret và PII trước khi response tới khách hàng.
2. **Egress boundary:** trước mọi network/tool action, code thuần quyết định URL và
   payload có được rời hệ thống hay không.

Model không tham gia quyết định allowlist. Một câu trả lời như “URL này an toàn”
không thể thay đổi kết quả policy.

```text
LLM response -> content_filter -> output an toàn -> khách hàng
                                  -> judge (chỉ nhận bản đã redact)

Proposed action -> parse URL -> exact hostname/scheme/port policy
                            -> scan payload
                            -> allow hoặc block trước sink
```

## 2. Workflow và logic triển khai

### Bước 1 — Lọc output bằng `content_filter`

Hàm trả đúng contract:

- `safe`: chỉ `True` khi không tìm thấy dữ liệu nhạy cảm.
- `issues`: loại vấn đề và số lượng match.
- `redacted`: nội dung đã thay mọi match bằng `[REDACTED]`.

Các nhóm được kiểm tra gồm password assignment, API key dạng `sk-...`, hostname
nội bộ, email, số điện thoại Việt Nam, CMND/CCCD và secret giả `admin123` của
lab. Regex dùng boundary để tránh match một đoạn nằm giữa chuỗi dài hơn.

### Bước 2 — Chặn output ngay trong plugin

`OutputGuardrailPlugin.after_model_callback`:

1. Tăng `total_count` và lấy text từ các response part.
2. Chạy `content_filter`; nếu có vấn đề thì thay content bằng bản đã redact và
   tăng `redacted_count`.
3. Nếu bật LLM judge, chỉ gửi **bản đã redact** sang judge. Việc này tránh biến
   safety judge thành một kênh egress phụ chứa chính secret đang cần bảo vệ.
4. Nếu judge kết luận unsafe, thay toàn bộ response bằng thông báo an toàn và
   tăng `blocked_count`.

Plugin luôn trả response đã kiểm soát. Nó không dựa vào việc input guard trước đó
có bắt được attack hay không.

### Bước 3 — Parse URL và so hostname tuyệt đối

`is_egress_allowed` dùng `urllib.parse.urlparse`, sau đó kiểm tra deterministic:

- Scheme phải là `https`.
- `parsed.hostname` phải là phần tử khớp hoàn toàn trong allowlist:
  `api.vinbank.example` hoặc `cases.vinbank.example`.
- Không cho URL chứa username/password và không cho port ngoài HTTPS 443.
- URL hoặc port không hợp lệ được fail closed.

Vì so sánh hostname tuyệt đối, `api.vinbank.example.evil.com` khác hoàn toàn
`api.vinbank.example` và bị block. Không dùng phép kiểm tra substring
`"vinbank.example" in url`.

### Bước 4 — Kiểm tra payload trước egress

Payload được chuẩn hoá Unicode NFKC và bỏ format/zero-width character trước khi
scan. Nếu chứa password, `admin123`, API key, internal host, phone, email hoặc
CMND/CCCD thì hàm trả `False`, kể cả destination hợp lệ.

Bảng quyết định chính:

| Destination/payload | Kết quả | Lý do |
| --- | --- | --- |
| `https://api.vinbank.example/v1/transfers`, payload thường | Allow | HTTPS, hostname đúng, payload sạch |
| `https://api.vinbank.example.evil.com/...` | Block | Hostname không khớp tuyệt đối |
| `https://evil.example/collect` | Block | Không thuộc allowlist |
| Host hợp lệ nhưng có secret/phone/email | Block | Dữ liệu nhạy cảm không được egress |

`is_egress_allowed` là policy cho destination và dữ liệu. Việc chuyển tiền còn là
high-risk action và ở production phải đi qua authorization/HITL riêng; một kết
quả egress `True` không đồng nghĩa action đã được phê duyệt.

## 3. Cách kiểm tra

Từ thư mục gốc repository:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/public/test_lab_contracts.py -q
.\.venv\Scripts\python.exe -m pytest tests/smoke -q
```

Nên kiểm tra thêm các biến thể:

- Subdomain giả, HTTP, userinfo URL và port lạ.
- Payload có `admin123`, `sk-...`, internal DB, số điện thoại và email.
- Response chứa nhiều loại PII cùng lúc phải redact hết.
- Response sạch giữ nguyên nội dung và `safe=True`.
- Plugin cập nhật đúng `total_count`, `redacted_count`, `blocked_count`.

## 4. Giới hạn và hướng production

Regex phù hợp cho lớp chặn deterministic của lab nhưng production cần data
classification mạnh hơn, structured payload validation, tokenization/DLP, audit
theo request ID và deny-by-default tại network gateway. Allowlist cũng nên nằm
trong cấu hình được quản trị, không để model hay nội dung RAG sửa tại runtime.
