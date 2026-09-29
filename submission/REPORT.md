# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Văn Biển
- **MSSV:** 2A202602416
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/nguyenbien8/K4-L3-DAY13-NguyenVanBien-2A202602416-Monitoring-LLMOps
- **Commit SHA cuối:** `2dd6cba` (cp4 — commit chứa toàn bộ source, config, evidence và kết quả tests/validators cuối); các commit sau đó chỉ sửa thông tin học viên trong REPORT, không đổi code/evidence
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311)
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602416`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) + [`evidence/06-08-trace-summary.txt`](evidence/06-08-trace-summary.txt) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png) + [`evidence/06-08-trace-summary.txt`](evidence/06-08-trace-summary.txt) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt rollback | [`evidence/10-prompt-rollback.png`](evidence/10-prompt-rollback.png) (trái: production → v2; phải: rollback về v1) + [`evidence/10-prompt-rollback.txt`](evidence/10-prompt-rollback.txt) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) + [`evidence/14-incident-trace.txt`](evidence/14-incident-trace.txt) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 — thiếu `correlation_id` (MISSING), thiếu enrichment, 0 correlation ID ([output](evidence/00-baseline-log-validator.txt)) | 100/100 (192 records, 93 correlation ID, 0 PII leak) | Log baseline được chuyển ra ngoài repo trước khi đo lại |
| `validate_dashboard.py` | HỢP LỆ 6/6 ([output](evidence/00-baseline-dashboard-validator.txt)) | HỢP LỆ 6/6 | Contract giữ nguyên; dashboard runtime dựng từ `data/logs.jsonl` |
| `pytest` | 22 passed ([output](evidence/00-baseline-pytest.txt)) | 33 passed ([output](evidence/01-pytest.txt)) | Thêm tests middleware, PII, child observations |
| Số traces hợp lệ | Trace chỉ có 1 observation (`lab-agent-run`) | ~96 traces trong project ([06](evidence/06-trace-list.png): Total ≈ 96), đều có AGENT → RETRIEVER + GENERATION; chi tiết 24 trace đợt prompt trong [summary](evidence/06-08-trace-summary.txt) | Mỗi trace có `correlation_id` trong metadata |
| Số PII leak | 0 (starter đã dùng `summarize_text` cho preview) | 0 trên 192 records — scrub toàn bộ event trước khi ghi file | Thêm processor + pattern passport, tests cho CCCD/thẻ |
| Latency P95 / TTFT P95 | 2663 ms / 50 ms (10 request, `/metrics`; request đầu chậm do fetch prompt lần đầu) | 1841 ms / 50 ms (76 request, dashboard) | Steady-state ~155 ms; request chậm là request đầu sau restart (cold fetch prompt) |
| Retrieval success rate | 100% (10/10 `tool_success=true`) | 100% (incident `rag_slow` làm chậm, không làm lỗi retrieval) | Retrieval success không phát hiện được `rag_slow`; cần latency theo span |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** [`app/middleware.py`](../app/middleware.py) gọi `clear_contextvars()` đầu mỗi request, nhận header `x-request-id` nếu đúng format `req-<8-hex>` (header sai format bị bỏ, sinh ID mới bằng `uuid4().hex[:8]` để tránh log injection), bind vào structlog contextvars, gán `request.state.correlation_id` để agent đưa vào trace metadata và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, `user_id_hash` (SHA-256 cắt 12 ký tự, không ghi user_id gốc), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`. Context được bind trong [`app/main.py`](../app/main.py) trước dòng `request_received`, nên mọi log sau đó trong request đều mang cùng metadata.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` trong [`app/logging_config.py`](../app/logging_config.py) được đặt sau `format_exc_info` (để cả stack trace dạng text cũng bị scrub) và **trước** `JsonlFileProcessor`/`JSONRenderer`; nó scrub đệ quy mọi string trong event (dict/list lồng nhau), không chỉ `payload`. [`app/pii.py`](../app/pii.py) có pattern email, thẻ thanh toán, CCCD 12 số, điện thoại VN (0/+84, có khoảng trắng/chấm/gạch) và hộ chiếu VN; thẻ và CCCD được che trước điện thoại để tránh cắt nhầm chuỗi số dài.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 100/100; gửi request chứa email/điện thoại/CCCD/thẻ giả với `x-request-id: req-0000beef` → response trả đúng ID và log chỉ còn `[REDACTED_*]` ([05](evidence/05-pii-redaction.txt)); tests mới trong [`tests/test_pii.py`](../tests/test_pii.py) và [`tests/test_middleware.py`](../tests/test_middleware.py) kiểm tra định dạng ID, tái sử dụng header hợp lệ, từ chối header sai và không rò context giữa hai request.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** key trong `.env` thuộc project `day13-k4-l3a-2A202602416` (`auth_check()` = True); mọi trace có `correlation_id` trùng với dòng trong `data/logs.jsonl` do tôi chạy `load_test.py`. [`scripts/export_traces.py`](../scripts/export_traces.py) gọi Langfuse API v2 observations để liệt kê 24 trace kèm correlation ID (bỏ các field `scope.*` chứa public key).
- **Cấu trúc root/retrieval/generation observations:** root `lab-agent-run` (type `agent`, `@observe`) → child `retrieval` (type `retriever`, input là `query_preview` đã scrub, output `doc_count`, metadata `tool_success`, `level=ERROR` khi lỗi) → child `llm-generate` (type `generation`, có `model`, `prompt` managed của Langfuse, `usage_details` input/output/total, `cost_details` input/output/total theo giá $3/$15 per 1M token, `completion_start_time` để Langfuse tính TTFT). Không capture raw prompt/output, chỉ preview đã qua `scrub_text` ([`app/agent.py`](../app/agent.py), helper [`app/tracing.py`](../app/tracing.py)).
- **Cách nối trace với log:** `correlation_id` được đưa vào trace metadata qua `propagate_attributes` (vì vậy có ở cả root và mọi child), và log `response_sent` ghi thêm `trace_id` lấy từ `get_current_trace_id()`. Từ log có thể mở thẳng trace, từ trace có thể lọc log theo `correlation_id`.
- **Prompt name:** `day13-chat` (text prompt, 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`)
- **Version/label baseline:** v1, labels `baseline` + `production`, template gốc
- **Version/label candidate:** v2, label `candidate`, thêm dòng "Answer concisely in at most 3 sentences and cite the docs." (cùng input: `tokens_in` 32 → 47)
- **Trace ID của mỗi version:** baseline/v1 `req-0000b005` → `8f5417c7dc313ba7e42b0440a18625ee`; candidate/v2 `req-0000c002` → `5a7e136d0eb17ed1372df985ab1e7cd6`; production sau promote (v2) `req-0000d003` → `b6e58ea78f89eb70be9250abc42f5739`; production sau rollback (v1) `req-0000e004` → `87bdcab013c80f4de71243ba053b4d02`
- **Cách promote và rollback `production`:** dùng `update_prompt(name="day13-chat", version=2, new_labels=["production","candidate"])` để promote (08:02:51 UTC), restart API để bỏ cache 60 s, chạy request → trace ghi v2; sau đó `update_prompt(version=1, new_labels=["production","baseline"])` để rollback (08:03:03 UTC) → request tiếp theo ghi v1. App không cần deploy lại, chỉ đổi label trên Langfuse ([10](evidence/10-prompt-rollback.txt)).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [`scripts/build_dashboard.py`](../scripts/build_dashboard.py) đọc `data/logs.jsonl` và `config/dashboard.yaml`, dựng đúng 6 panel (latency P50/P95/P99 + TTFT P95; traffic req/phút; error rate + retrieval success + breakdown; cost/phút + cumulative; tokens in/out; quality mean), time range 60 phút, đơn vị và threshold lấy từ contract ([11](evidence/11-dashboard-overview.png)). Baseline: P95 1841 ms, TTFT P95 50 ms, error 0%, retrieval 100%, cost $0.154/76 request, quality 0.874.
- **SLO và lý do chọn:** `fast_successful_requests`, 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày ([`config/slo.yaml`](../config/slo.yaml)). Baseline P99 2253 ms, steady-state ~155 ms; request chậm chỉ là cold fetch prompt. Ngưỡng 3000 ms trùng threshold dashboard, còn ~0.7 s headroom trên P99 nhưng vẫn bắt được `rag_slow` (+2.5 s). Chọn 99.5% thay vì 99.9% vì app phụ thuộc Langfuse Cloud bên ngoài và chỉ có một instance.
- **Cách tính error budget:** budget = 100% − 99.5% = 0.5% bad event. Với 100,000 request/28 ngày, được phép 500 request chậm hoặc lỗi; nếu hỏng toàn phần thì tương đương 0.5% × 28 × 24 × 60 = 201.6 phút. Burn rate: fast burn 14.4× (đốt 2% budget trong 1 h), slow burn 6× (5% trong 6 h).
- **Ba alert và runbook tương ứng:** [`config/alert_rules.yaml`](../config/alert_rules.yaml) + [`docs/alerts.md`](../docs/alerts.md): (1) `HighLatencyP95` P2, P95 > 3000 ms trong 5m; (2) `HighErrorRate` P1, error rate > 2% hoặc retrieval success < 90% trong 5m; (3) `CostPerRequestSpike` P3, cost/request > 0.004 USD (2× baseline) trong 15m. Cả ba gửi Slack `#day13-k4-l3a-alerts`, owner `nguyenvanbien-oncall`, runbook có 3 bước kiểm tra theo Metrics → Logs → Traces và mitigation.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (file riêng của lớp, lưu tại `config/challenge.json`, không commit)
- **Khoảng thời gian điều tra:** 2026-09-29 08:39:46 → 08:40:02 UTC (inject lúc 08:39:46, tắt sau khi thu evidence); so sánh với traffic bình thường 08:39:40–08:39:42 ngay trước đó.
- **Triệu chứng từ metrics:** panel Latency: P50/P95 của phút 08:40 tăng từ ~153 ms lên **2654 ms**, vượt `latency_threshold_ms` 2000 của challenge (P95 bình thường 155 ms). TTFT P95 vẫn 50 ms, error rate 0%, retrieval success 100%, cost/tokens/quality không đổi. Như vậy chậm không nằm ở LLM và không phải lỗi, chỉ ảnh hưởng feature `monitoring` ([12](evidence/12-incident-metric.png)). Phía client đo được 8–13 s/request.
- **Log line và correlation ID liên quan:** lọc `response_sent` có `latency_ms > 2000` → 5 request, đều `feature=monitoring`, `tool_success=true`. Chọn `req-a2bbad00`: `latency_ms=2653, ttft_ms=50, trace_id=531fc82d86e6a99ebc322da2369cb17c` (08:39:51.571Z). Timeline log cho thấy request sau chỉ được `request_received` khi request trước đã `response_sent`, nghĩa là các request bị xử lý tuần tự ([13](evidence/13-incident-log.txt)).
- **Trace ID và span gây ảnh hưởng:** trace `531fc82d86e6a99ebc322da2369cb17c` (metadata `correlation_id=req-a2bbad00`): root `lab-agent-run` 2655 ms, trong đó span **`retrieval` 2501 ms** (~94%), `llm-generate` chỉ 152 ms. Trace bình thường `84deee9acb1fc4e0e49f8efb4276e78b` (`req-e8e93506`) có `retrieval` 1 ms ([14](evidence/14-incident-trace.txt)).
- **Root cause:** bước retrieval (vector store/RAG, `app/mock_rag.retrieve`) bị chậm thêm ~2.5 s mỗi lần gọi (incident `rag_slow`). Vì retrieval là lời gọi đồng bộ chạy trong endpoint `async`, nó chặn event loop, nên các request đồng thời phải xếp hàng và client chờ tới ~13 s.
- **Fix action:** tắt incident / khôi phục vector store (`python scripts/inject_incident.py --disable`); đặt timeout ngắn cho retrieval (ví dụ 500 ms) và fallback trả lời không có context khi quá hạn; chạy retrieval ngoài event loop (`run_in_threadpool` hoặc client async) để một request chậm không chặn các request khác.
- **Preventive measure:** alert `HighLatencyP95` (P95 > 3000 ms/5m) cộng thêm cảnh báo riêng khi span `retrieval` > 1000 ms; ghi `retrieval_ms` vào log để dashboard tách được latency theo bước; thêm load test concurrency 5 vào kiểm tra trước deploy để phát hiện lời gọi blocking.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** chỉ gửi preview đã scrub (`summarize_text`) vào input/output của observation thay vì raw prompt/output. Raw prompt chứa nguyên câu hỏi người dùng (có email, số thẻ trong sample queries), nếu gửi lên Langfuse thì PII rò sang hệ thống thứ ba dù log đã sạch. Đổi lại vẫn giữ được model, usage, cost, prompt version để debug, và `correlation_id`/`trace_id` để tra ngược log khi cần chi tiết.
- **Một lỗi/blocker đã gặp:** (1) trace của request dùng label `baseline` (`req-0000b001`) không xuất hiện trên Langfuse; (2) API cũ `GET /api/public/traces/{id}` trả 410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`.
- **Cách tìm nguyên nhân và xử lý:** (1) log có `response_sent` nhưng Langfuse không có trace, nên lỗi nằm ở bước export. Langfuse SDK gửi span theo batch nền, mà tôi đã kill process ngay sau request nên buffer bị mất. Tôi thêm `get_langfuse_client().flush()` trong lifespan shutdown của [`app/main.py`](../app/main.py), chờ exporter trước khi restart, rồi chạy lại (`req-0000b005`). (2) đọc thông báo lỗi và chuyển sang `GET /api/public/v2/observations` trong [`scripts/export_traces.py`](../scripts/export_traces.py).
- **Cách hiểu luồng Metrics → Logs → Traces:** metrics trả lời *có vấn đề gì và khi nào*: P95 tăng lên 2654 ms lúc 08:40 trong khi TTFT/error/cost bình thường, nên loại trừ LLM và lỗi. Logs trả lời *request nào bị ảnh hưởng*: lọc `latency_ms > 2000` ra 5 request `feature=monitoring`, lấy `req-a2bbad00` và `trace_id`. Traces trả lời *bước nào là nguyên nhân*: span `retrieval` chiếm 2501/2655 ms. `correlation_id` là khóa nối log và trace; mỗi lớp thu hẹp phạm vi cho lớp sau.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt là "code" của LLM app nhưng đổi được không cần deploy. Label + version trong trace cho biết chính xác request nào dùng prompt nào (v2 làm `tokens_in` tăng 32 → 47, tức ~47% chi phí input). Nếu v2 làm hỏng chất lượng hoặc đội cost, chỉ cần chuyển label `production` về v1 là rollback trong vài giây, có trace chứng minh. SLO/error budget biến "chậm" thành con số có thể ra quyết định (được phép 0.5% request > 3 s), còn alert cost/request phát hiện prompt hoặc output dài bất thường trước khi vượt ngân sách.
- **Điều quan trọng nhất đã học:** observability phải được thiết kế để *nối* được các tín hiệu. Metric đẹp mà không có correlation ID thì không tìm được request, trace không có child span thì không khoanh vùng được bước chậm. Redaction phải xảy ra trước khi dữ liệu rời process, cả với log lẫn trace.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** `latency_ms` chỉ đo thời gian trong agent nên không thấy thời gian xếp hàng khi event loop bị chặn (server 2.65 s, client 8–13 s); nên log thêm thời gian của middleware (`x-response-time-ms`). Fix action trong CP3 (timeout/fallback, `run_in_threadpool`) mới được đề xuất, chưa triển khai. Dashboard là ảnh tĩnh sinh bằng script, chưa phải dashboard live có refresh; alert rules mới là cấu hình, chưa nối Slack thật.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo đã được nộp trên VLearn LMS (LMS chỉ có ô nộp link; commit SHA ghi ở mục 1).
