# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Văn Biên
- **MSSV:** 2A202602416
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/nguyenbien8/K4-L3-DAY13-NguyenVanBien-2A202602416-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602416`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 — thiếu `correlation_id` (MISSING), thiếu enrichment, 0 correlation ID ([output](evidence/00-baseline-log-validator.txt)) | 100/100 sau CP1 (23 records, 11 correlation ID, 0 PII leak) | Log baseline được chuyển ra ngoài repo trước khi đo lại |
| `validate_dashboard.py` | HỢP LỆ 6/6 ([output](evidence/00-baseline-dashboard-validator.txt)) | | |
| `pytest` | 22 passed ([output](evidence/00-baseline-pytest.txt)) | | |
| Số traces hợp lệ | | | |
| Số PII leak | 0 (starter đã dùng `summarize_text` cho preview) | 0 — scrub toàn bộ event trước khi ghi file | Thêm processor + pattern passport, tests cho CCCD/thẻ |
| Latency P95 / TTFT P95 | 2663 ms / 50 ms (10 request, `/metrics`; request đầu chậm do fetch prompt lần đầu) | | |
| Retrieval success rate | 100% (10/10 `tool_success=true`) | | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** [`app/middleware.py`](../app/middleware.py) gọi `clear_contextvars()` đầu mỗi request, nhận header `x-request-id` nếu đúng format `req-<8-hex>` (header sai format bị bỏ, sinh ID mới bằng `uuid4().hex[:8]` để tránh log injection), bind vào structlog contextvars, gán `request.state.correlation_id` để agent đưa vào trace metadata và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256 cắt 12 ký tự, không ghi user_id gốc), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`. Context được bind trong [`app/main.py`](../app/main.py) trước dòng `request_received`, nên mọi log sau đó trong request đều mang cùng metadata.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` trong [`app/logging_config.py`](../app/logging_config.py) được đặt sau `format_exc_info` (để cả stack trace dạng text cũng bị scrub) và **trước** `JsonlFileProcessor`/`JSONRenderer`; nó scrub đệ quy mọi string trong event (dict/list lồng nhau), không chỉ `payload`. [`app/pii.py`](../app/pii.py) có pattern email, thẻ thanh toán, CCCD 12 số, điện thoại VN (0/+84, có khoảng trắng/chấm/gạch) và hộ chiếu VN; thẻ và CCCD được che trước điện thoại để tránh cắt nhầm chuỗi số dài.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 100/100; gửi request chứa email/điện thoại/CCCD/thẻ giả với `x-request-id: req-0000beef` → response trả đúng ID và log chỉ còn `[REDACTED_*]` ([05](evidence/05-pii-redaction.txt)); tests mới trong [`tests/test_pii.py`](../tests/test_pii.py) và [`tests/test_middleware.py`](../tests/test_middleware.py) kiểm tra định dạng ID, tái sử dụng header hợp lệ, từ chối header sai và không rò context giữa hai request.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
- **Cấu trúc root/retrieval/generation observations:**
- **Cách nối trace với log:**
- **Prompt name:**
- **Version/label baseline:**
- **Version/label candidate:**
- **Trace ID của mỗi version:**
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
- **SLO và lý do chọn:**
- **Cách tính error budget:**
- **Ba alert và runbook tương ứng:**

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
