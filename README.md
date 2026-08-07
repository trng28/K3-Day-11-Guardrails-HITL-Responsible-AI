# Day 11 — Controlled Agent Security (2026)

<p align="center">
  <img src="./assets/Pi7_Gif.gif" alt="VinBank Guardrails live demo" width="100%" />
</p>

## Tình huống

Chatbot ngân hàng **VinBank**. Agent “unsafe” cố ý chứa mật khẩu / API key trong system prompt.

```
Câu hỏi người dùng
    → Rate Limiter
    → Lọc đầu vào (Input Guardrails)
    → LLM trả lời
    → Lọc đầu ra (Output Guardrails + Judge)
    → Audit / Monitoring
    → Phản hồi
```

---

## End-to-end workflow

### 1. Luồng một request từ browser đến response

```text
React UI (:8080)
  → POST /api/chat qua Nginx reverse proxy
  → FastAPI tạo request_id và ghi audit input
  → RateLimitPlugin kiểm tra sliding window theo user_id
  → InputGuardrailPlugin
      ├─ chuẩn hoá Unicode NFKC, zero-width và whitespace
      ├─ phát hiện direct/indirect prompt injection
      └─ chặn chủ đề cấm hoặc ngoài phạm vi ngân hàng
  → OpenAI Responses API — gpt-4o-mini
  → OutputGuardrailPlugin
      ├─ redact password, API key và internal host
      ├─ redact phone, email và CMND/CCCD
      └─ LLM safety judge (bật bằng USE_LLM_JUDGE=true)
  → ConfidenceRouter / HITL
      ├─ action thường + confidence ≥ 0.90 → auto_send
      ├─ confidence 0.70–<0.90 → queue_review
      ├─ confidence < 0.70 → escalate
      └─ mọi HIGH_RISK_ACTIONS → escalate bất kể confidence
  → Audit output với cùng request_id, layer, latency và reviewer/action decision
  → Monitoring cập nhật block rate, rate-limit hits và judge fail rate
  → JSON response trả về React để hiển thị nội dung, layer, HITL và telemetry
```

Input bị chặn ở rate limiter hoặc input guardrail sẽ không được gửi tới OpenAI.
Response có dữ liệu nhạy cảm được redact trước khi tới browser hoặc safety judge.

### 2. Action và egress boundary

Model chỉ được **đề xuất** action. Trước khi có side effect, code deterministic
phải kiểm tra:

```text
Proposed action
  → HIGH_RISK_ACTIONS? → yêu cầu approval có reviewer
  → parse URL bằng urllib.parse
  → scheme phải là HTTPS
  → hostname phải khớp tuyệt đối allowlist
  → payload không được chứa secret hoặc PII
  → allow hoặc fail closed trước network/tool sink
```

`api.vinbank.example.evil.com` không khớp `api.vinbank.example`. Timeout/reject
không bao giờ tự chuyển tiền. Web demo hiện không gắn transfer tool thật.

### 3. Audit, monitoring và incident trace

- `record_input()` tạo hoặc nhận `request_id`.
- `record_output()` dùng lại đúng ID và lưu layer, `latency_ms`, reviewer/action decision.
- `GET /api/audit/{request_id}` truy vấn toàn bộ record của một request.
- `GET /api/metrics` trả monitoring snapshot và active alerts.
- `outputs/audit_log.json`, `outputs/metrics.json`, `outputs/results.json` là artifact
  của assignment suite.

### 4. Red-team workflow

```text
adversarial_prompts
  → run_attacks(target thật)
  → lưu response thật + response_source=live_target_call
  → classify leak / input block / output block / model refusal
  → outputs/unsafe_attack_result.json
  → outputs/guards_attack_result.json
  → outputs/attack_results.json
```

Bộ prompt phủ direct, indirect, obfuscation, social engineering và action/egress.
Grader bonus tự replay Guards Agent với canary mới, không tin kết quả tự khai.

### 5. Chạy end-to-end bằng Docker

```powershell
Copy-Item .env.example .env
# Điền OPENAI_API_KEY trong .env

docker compose up --build -d
```

Sau khi hai container healthy:

- Web UI: <http://localhost:8080>
- API health: <http://localhost:8080/api/health>
- Backend chỉ nằm trong Docker network ở port `8000`; Nginx expose port `8080`.

```powershell
docker compose ps
docker compose logs -f backend
docker compose down
```

Kiểm tra repository và sinh artifact:

```powershell
pytest tests/public tests/smoke -q
cd src
python main.py --part 1   # red-team target thật
python main.py --part 5   # results + audit + metrics
```

---

## Làm bài trên máy

> Đã cài môi trường ở mục **Cài đặt môi trường** phía trên chưa? Nếu chưa thì làm trước.

### Phần A — Phòng thủ

**Thứ tự:** sửa TODO trong file → rồi mới chạy lệnh. Chi tiết: [`assignment11.md`](assignment11.md) §5.

| Làm trước | File |
|-----------|------|
| TODO **1–3** | `src/guardrails/input_guardrails.py` |
| TODO **4–6** | `src/guardrails/output_guardrails.py` |
| TODO **7** (tuỳ chọn) | `src/guardrails/nemo_guardrails.py` |
| TODO **8** (+ egress 8A) | `src/assignment/*.py` → rồi `python main.py --part 5` |
| TODO **9–10** | `src/testing/testing.py` |
| TODO **11–12** | `src/hitl/hitl.py` |
| TODO **13–14** (phần B) | `src/attacks/attacks.py` |

Sau khi đã code, kiểm:

```powershell
cd src
python main.py --part 2    # sau TODO 1–6 (+7 NeMo)
python main.py --part 3    # sau TODO 9–10
python main.py --part 4    # sau TODO 11–12
python main.py --part 5    # sau TODO 8 → outputs/results.json (+ audit/metrics)
```

```powershell
pytest tests/smoke -q
pytest tests/public -q
python scripts/grade.py --submission-dir . --out outputs/grade_report.json
```

Viết `report/<MSSV>_report.md`.

### Phần B — Red team và bonus

1. Viết ≥5 prompt vào `src/attacks/attacks.py`
2. Chạy (tấn công **unsafe** rồi **guards**):

```powershell
cd src
python main.py --part 1
```

3. Unsafe = attack target để phân tích. Guards (`src/agents/guards_agent.py`) = **bonus chỉ khi verifier replay xác nhận leak**.
4. Lưu `outputs/attack_results.json` làm evidence; không tự cấp runtime score hoặc bonus.

Colab / Jupyter (tuỳ chọn): `notebooks/lab11_guardrails_hitl.ipynb`. Local là đủ.

Nộp theo [`SUBMISSION.md`](SUBMISSION.md).

---

## Cấu trúc repo

```
├── assignment11.md                    ← Đề bài duy nhất
├── SUBMISSION.md                      ← Quy định nộp
├── data/pii_hallucination_samples.json ← PII + ground_truth đối chiếu hallucination
├── frontend/                            ← React + TypeScript + Nginx
├── Dockerfile                           ← FastAPI backend image
├── docker-compose.yml                   ← Backend + frontend deployment
├── src/
│   ├── assignment/                    ← Hạng mục A (Phòng thủ) — starters
│   ├── attacks/                       ← Hạng mục B (Tấn công)
│   ├── agents/security_boundary.py    ← Reference provenance / action boundary
│   ├── agents/guards_agent.py         ← Guards Agent (mục tiêu bonus)
│   ├── guardrails/ testing/ hitl/     ← Module hỗ trợ phòng thủ
│   ├── core/openai_runtime.py          ← OpenAI Responses API runtime
│   ├── web_api.py                      ← FastAPI chat/metrics/audit API
│   └── main.py
├── notebooks/lab11_guardrails_hitl.ipynb
├── schemas/results.schema.json
├── scripts/grade.py
├── tests/
├── Slide_Lab_Day11.html
└── .env.example
```

---

## Tài liệu tham khảo

- [OWASP Top 10 for LLM](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails)
- [OpenAI API quickstart](https://platform.openai.com/docs/quickstart)
- [AI Safety Fundamentals](https://aisafetyfundamentals.com/)

## Live web demo

Repository có giao diện React + TypeScript và FastAPI backend. Chạy bằng Docker:

```powershell
docker compose up --build
```

Mở `http://localhost:8080`. Xem hướng dẫn chi tiết tại
[`docs/live-demo.md`](docs/live-demo.md).
