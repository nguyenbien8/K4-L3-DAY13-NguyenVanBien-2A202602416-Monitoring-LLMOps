# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Rule nằm trong [`../config/alert_rules.yaml`](../config/alert_rules.yaml), SLO trong [`../config/slo.yaml`](../config/slo.yaml). Nguồn dữ liệu là `data/logs.jsonl` (dashboard: `python scripts/build_dashboard.py`), trace nằm trong project Langfuse `day13-k4-l3a-2A202602416`.

Luồng điều tra chung: **Metrics → Logs → Traces**. Dashboard cho biết triệu chứng và khoảng thời gian. Lọc log trong khoảng đó để lấy `correlation_id` và `trace_id`. Mở trace cùng ID để so sánh span `retrieval` và `llm-generate`.

## Alert 1 HighLatencyP95

- Tên: `HighLatencyP95`
- Severity: P2 (ảnh hưởng trải nghiệm, chưa mất chức năng)
- Duration: 5m
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests`, tức là 99.5% request trả `response_sent` với `latency_ms <= 3000` trong 28 ngày
- Điều kiện và thời gian duy trì: P95 của `response_sent.latency_ms` lớn hơn 3000 ms, duy trì liên tục 5 phút
- Ảnh hưởng tới người dùng: câu trả lời chậm hơn 3 s và error budget latency bị đốt nhanh
- Ba bước kiểm tra đầu tiên:
  1. Mở panel **Latency percentiles and TTFT**. Nếu TTFT P95 vẫn khoảng 50 ms mà P95 tăng, chậm nằm ngoài bước sinh token đầu, tức ở retrieval, fetch prompt hoặc queue. Ghi lại khoảng thời gian bắt đầu tăng.
  2. Lọc log chậm, ví dụ `python -c "import json;[print(r['correlation_id'],r.get('trace_id'),r['latency_ms'],r.get('feature')) for r in map(json.loads,open('data/logs.jsonl',encoding='utf-8')) if r.get('event')=='response_sent' and r['latency_ms']>3000]"`, rồi xem request chậm có tập trung vào một `feature` hay không.
  3. Mở trace theo `trace_id` hoặc `correlation_id` và so sánh độ dài span `retrieval`, `llm-generate` với phần còn lại của root `lab-agent-run`.
- Mitigation tạm thời:
  - Retrieval chậm: tắt hoặc thay nguồn retrieval, trả fallback doc và giảm timeout vector store.
  - Fetch prompt chậm: tăng `cache_ttl_seconds` hoặc warm-up prompt khi khởi động.
  - Chỉ LLM chậm: đổi sang model nhanh hơn.
- Owner: `nguyenvanbien-oncall`

## Alert 2 HighErrorRate

- Tên: `HighErrorRate`
- Severity: P1 (người dùng nhận HTTP 500)
- Duration: 5m
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: `fast_successful_requests` (request lỗi là bad event) và guardrails `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received)` lớn hơn 2%, hoặc retrieval success dưới 90%, duy trì 5 phút
- Ảnh hưởng tới người dùng: request thất bại, không có câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở panel **Error rate and retrieval success**, xem breakdown `error_type` và retrieval success giảm từ lúc nào.
  2. Lọc log `event == "request_failed"`, đọc `error_type`, `tool_name`, `payload.detail` (đã scrub PII) và lấy `correlation_id`.
  3. Tìm trace của `correlation_id` đó. Span nào có `level=ERROR`, ví dụ `retrieval` với `status_message=RuntimeError`, là nơi phát sinh lỗi.
- Mitigation tạm thời: nếu lỗi ở retrieval (vector store timeout), bật fallback trả lời không có context kèm cảnh báo, thêm retry có backoff và circuit breaker; nếu lỗi do deploy mới, rollback phiên bản hoặc prompt label `production`.
- Owner: `nguyenvanbien-oncall`

## Alert 3 CostPerRequestSpike

- Tên: `CostPerRequestSpike`
- Severity: P3 (chưa ảnh hưởng chức năng nhưng đốt ngân sách)
- Duration: 15m
- Kênh thông báo: Slack `#day13-k4-l3a-alerts`
- SLI/SLO liên quan: guardrails `avg_cost_per_request_usd_max: 0.004` (khoảng 2 lần baseline 0.002 USD/request) và `daily_cost_usd_max: 2.5`
- Điều kiện và thời gian duy trì: `sum(cost_usd) / count(response_sent)` lớn hơn 0.004 USD, duy trì 15 phút
- Ảnh hưởng tới người dùng: câu trả lời dài bất thường; ngân sách ngày có thể cạn và dẫn tới bị giới hạn dịch vụ
- Ba bước kiểm tra đầu tiên:
  1. Mở panel **Cost over time** và **Input and output tokens** để xác định chi phí tăng do `tokens_in` (prompt dài) hay `tokens_out` (output dài).
  2. Lọc log `response_sent` có `cost_usd` cao, lấy `correlation_id`, `feature` và `tokens_out`.
  3. Mở trace, đọc `usage_details`, `cost_details` và prompt name/version trên generation `llm-generate`; nếu vừa promote prompt mới thì so sánh với version trước.
- Mitigation tạm thời: đặt `max_tokens` cho output, rollback label `production` về prompt version trước, hoặc định tuyến feature tốn kém sang model rẻ hơn.
- Owner: `nguyenvanbien-oncall`
