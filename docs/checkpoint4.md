# Checkpoint 4 — Lưu log và tạo cảnh báo

## 1. Phân tích yêu cầu

Observability phải trả lời được ba câu hỏi sau sự cố:

1. Request nào liên quan?
2. Guardrail/policy layer nào đã cho qua hoặc chặn?
3. Reviewer hoặc action gateway đã quyết định gì?

`request_id` là correlation key xuyên suốt. Thời gian bắt đầu được lưu khi nhận
input và chỉ kết thúc khi ghi output, nhờ đó latency phản ánh toàn bộ thời gian xử
lý thay vì thời gian của riêng một callback.

```text
record_input -> request_id -> guardrail/model/HITL/action -> record_output
                    |                                      |
                    +------------- audit events -----------+
                                      |
                              find_by_request_id
```

## 2. Workflow và logic triển khai

### Bước 1 — Ghi input và tạo correlation ID

`AuditLogPlugin.record_input()` nhận `request_id` từ upstream hoặc tạo ID dạng
`REQ-...`, lưu monotonic start time và append một input event. Hàm trả lại ID để
caller truyền nguyên giá trị đó qua toàn pipeline.

Input event gồm `request_id`, timestamp UTC, user, text, `layer=input` và quyết
định `received`.

### Bước 2 — Ghi output và quyết định

`record_output()` dùng request ID đã có, tính `latency_ms`, rồi lưu:

- Layer đã xử lý, trạng thái blocked và quyết định allow/block.
- Reviewer ID và reviewer decision nếu request qua HITL.
- Action cùng action decision nếu agent đề xuất side effect.
- Metadata bổ sung khi pipeline cần lưu risk signal, approval ID hoặc reason.

Nếu caller không truyền ID trong một luồng tuần tự, logger có thể dùng request
đang mở gần nhất của user. Production có concurrency nên vẫn phải truyền ID rõ
ràng; không nên dựa vào fallback này.

`find_by_request_id()` trả toàn bộ input/output event liên quan để điều tra.

### Bước 3 — Tính metric và phát cảnh báo

`MonitoringAlert.check_metrics()` tính:

- `block_rate = blocked_requests / total_requests`.
- `judge_fail_rate = judge_fails / judge_checks`.
- Số `rate_limit_hits` tích luỹ trong monitoring window.

Alert được tạo khi giá trị **lớn hơn** threshold tương ứng. Mỗi lần check thay
snapshot alert hiện tại thay vì append lặp lại cùng một cảnh báo.

Các tên metric ổn định là `block_rate`, `rate_limit_hits` và
`judge_fail_rate`, thuận tiện cho dashboard hoặc alert routing.

### Bước 4 — Export

`AuditLogPlugin.export_json()` và `MonitoringAlert.export_json()` tự tạo thư mục
cha và ghi UTF-8 JSON. Monitoring export gọi `check_metrics()` trước nên file luôn
chứa alert mới nhất. `build_observability()` trả một audit logger và một monitor
đã sẵn sàng để pipeline sử dụng.

## 3. Mô phỏng spike và điều tra

Ví dụ kiểm tra không cần gọi LLM:

```python
from assignment.audit_log import AuditLogPlugin
from assignment.monitoring import MonitoringAlert

audit = AuditLogPlugin()
request_id = audit.record_input(user_id="customer-1", text="Transfer request")
audit.record_output(
    user_id="customer-1",
    text="Held for review",
    blocked=True,
    layer="hitl_transfer_review",
    request_id=request_id,
    reviewer_id="reviewer-7",
    reviewer_decision="reject",
    action="transfer_money",
    action_decision="not_executed",
)

records = audit.find_by_request_id(request_id)
assert len(records) == 2

monitor = MonitoringAlert()
monitor.total_requests = 10
monitor.blocked_requests = 8
monitor.rate_limit_hits = 9
monitor.judge_checks = 10
monitor.judge_fails = 5
alerts = monitor.check_metrics()
assert {alert.metric for alert in alerts} == {
    "block_rate", "rate_limit_hits", "judge_fail_rate"
}
```

Chạy test repository:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/public tests/smoke -q
```

## 4. Lưu ý production

Lab đang lưu text để dễ kiểm chứng. Production cần redact/tokenize PII trước khi
ghi log, mã hoá at rest, kiểm soát quyền xem, retention policy và immutable audit
storage. Counter cần có time window rõ ràng và alert deduplication/cooldown. Audit
failure không được phép làm high-risk action tự động đi tiếp.
