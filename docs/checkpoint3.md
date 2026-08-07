# Checkpoint 3 — Người duyệt quyết định việc rủi ro

## 1. Phân tích yêu cầu

Confidence chỉ mô tả mức chắc chắn của model, không phải quyền thực hiện action.
Model có thể rất tự tin nhưng vẫn hiểu sai khách hàng, bị prompt injection hoặc
đề xuất một thao tác không thể đảo ngược. Vì vậy:

- Action thông thường được route theo confidence.
- Mọi `HIGH_RISK_ACTIONS` luôn cần người duyệt, bất kể confidence.
- Timeout không bao giờ được coi như approval ngầm.
- Approval chỉ có hiệu lực với đúng action và diff mà reviewer đã xem.

```text
Agent response + confidence + action_type
    -> action thuộc HIGH_RISK_ACTIONS? -> escalate
    -> confidence không hợp lệ?        -> escalate (fail closed)
    -> confidence >= 0.90              -> auto_send
    -> confidence >= 0.70              -> queue_review
    -> còn lại                         -> escalate
```

## 2. Workflow và logic triển khai

### Bước 1 — Chuẩn hoá dữ liệu route

`action_type` được `strip()` và `casefold()` để khoảng trắng hoặc hoa/thường
không làm action rủi ro lọt qua. Confidence được đổi sang `float`. Giá trị không
phải số, NaN, vô cực hoặc ngoài `[0, 1]` đều được escalate theo fail-closed.

Danh sách rủi ro gồm chuyển tiền, đóng tài khoản, đổi mật khẩu, xoá dữ liệu, cập
nhật thông tin cá nhân và thêm/đổi beneficiary.

### Bước 2 — Áp dụng thứ tự ưu tiên

Kiểm tra high-risk diễn ra trước threshold:

| Điều kiện | Route | Priority | Cần người? |
| --- | --- | --- | --- |
| Bất kỳ `HIGH_RISK_ACTIONS` | `escalate` | high | Có |
| Confidence không hợp lệ | `escalate` | high | Có |
| Confidence `>= 0.90`, action thường | `auto_send` | low | Không |
| Confidence `>= 0.70` và `< 0.90` | `queue_review` | normal | Có |
| Confidence `< 0.70` | `escalate` | high | Có |

Do đó `transfer_money` confidence `0.99` vẫn không thể `auto_send`.

### Bước 3 — Thiết kế ba decision point

Ba điểm review trong `hitl_decision_points` là:

1. Chuyển tiền hoặc thay đổi beneficiary.
2. Đóng tài khoản hoặc xoá dữ liệu.
3. Đổi credential hoặc thông tin cá nhân.

Mỗi điểm mô tả đầy đủ trigger, mô hình HITL, action/diff và evidence reviewer cần
xem, ví dụ thực tế, kết quả approve/reject/timeout và audit fields.

Với beneficiary change, reviewer thấy người nhận cũ/mới, account ID, số tiền,
currency, nguồn tiền, xác nhận khách hàng, destination và fraud/anomaly signals.
Approval là scoped và single-use. Nếu amount hoặc beneficiary thay đổi thì phải
tạo review mới. Timeout giữ request và không gửi tiền.

### Bước 4 — Lifecycle quyết định

- **Approve:** tạo approval ID giới hạn đúng action/diff đã xem; gateway phía sau
  vẫn phải kiểm tra permission và egress policy.
- **Reject:** huỷ proposal, không tạo side effect; có thể mở fraud case nếu cần.
- **Timeout:** hold hoặc reject an toàn; tuyệt đối không tự thực thi.

Audit tối thiểu có `request_id`, action/intent, proposed action/diff,
`reviewer_id`, `reviewer_decision`, reason, timestamp, timeout status,
`approval_id` và `layer`. Nhờ `request_id`, input, review và action attempt có thể
được correlate trong cùng incident trail.

## 3. Cách kiểm tra

Từ thư mục gốc repository:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/public/test_lab_contracts.py -q
.\.venv\Scripts\python.exe -m pytest tests/smoke -q
```

Kiểm tra riêng phần HITL:

```powershell
Set-Location src
..\.venv\Scripts\python.exe main.py --part 4
```

Các ca biên nên test: confidence đúng `0.70`, đúng `0.90`, thấp hơn mỗi ngưỡng,
NaN/out-of-range, mọi phần tử của `HIGH_RISK_ACTIONS`, action viết hoa/thêm
khoảng trắng, và sự hiện diện của approve/reject/timeout/audit fields trong từng
decision point.

## 4. Giới hạn và hướng production

Router mới tạo quyết định, chưa tự xây review queue hoặc action executor. Trong
production cần lưu approval bất biến, TTL, reviewer authorization, separation of
duties, single-use token và atomic compare giữa approved diff với executed diff.
Nếu queue/audit store lỗi, high-risk action phải tiếp tục bị giữ thay vì bypass.
