# AWS Setup — Bedrock Claude + EC2 + Billing Alarms

Runbook to point the Agentic AI Hedge Fund at **Amazon Bedrock Claude** (tiered:
Haiku 4.5 workhorse + Sonnet 4.6 judge) and run the 3-month walk-forward (`--dev`
mode) on **EC2**, on your AWS credit, with **billing alarms** as a guardrail.

> All commands assume region **`us-east-2` (Ohio)**. Change `--region` if you enable the models elsewhere.

---

## 1. Enable Bedrock model access

Console → **Bedrock** → *Model access* → **Manage model access** → enable:
- **Anthropic — Claude Haiku 4.5**
- **Anthropic — Claude Sonnet 4.6**

Access is on-demand (per-token), matching the standard-tier pricing. No endpoint to provision.

## 2. Confirm the inference-profile IDs

Bedrock Claude is invoked via **cross-region inference profiles** (ids prefixed `us.`).
Get the exact ids and paste them into `config.py` (`WORKHORSE_MODEL`, `JUDGE_MODEL`):

```bash
aws bedrock list-inference-profiles --region us-east-2 \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId,'claude')].[inferenceProfileId,inferenceProfileName]" \
  --output table
```

Then in `config.py`:
```python
WORKHORSE_MODEL = "us.anthropic.claude-haiku-4-5-YYYYMMDD-v1:0"   # from the list above
JUDGE_MODEL     = "us.anthropic.claude-sonnet-4-6-YYYYMMDD-v1:0"
```

## 3. IAM permissions

Attach this policy to your IAM **user** (local dev) or EC2 **instance role** (preferred for EC2):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream"
    ],
    "Resource": [
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
      "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-*"
    ]
  }]
}
```
(The foundation-model wildcard across regions is required because the cross-region profile fans out to multiple regions.)

## 4. Credentials & environment

**Local dev** — IAM user access keys:
```bash
aws configure            # or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
```
`.env`:
```env
LLM_PROVIDER=bedrock
BEDROCK_REGION=us-east-2
# Leave LLM_MODEL UNSET so the workhorse defaults to Haiku and the Sonnet "judge"
# tier stays distinct (get_judge_llm picks JUDGE_MODEL explicitly).
FINDAT_API_KEY=...        # FinancialDatasets (data)
# BEDROCK_MAX_TOKENS=8192 # optional cost cap per call
```
**EC2** — no keys; the instance role from §3 is picked up automatically.

Smoke test (verifies creds/region/model + native tool-calling + usage metadata):
```bash
python -c "from llm import get_llm,get_judge_llm,get_usage_summary; \
print(get_llm('bedrock').invoke('say hi').content); \
print(get_judge_llm().invoke('say hi').content); print(get_usage_summary())"
```

## 5. Billing alarms (the guardrail)

Create an AWS **Budget** with alert thresholds, so a runaway loop can't silently drain the credit:

```bash
aws sns create-topic --name hedge-fund-billing --region us-east-1
aws sns subscribe --topic-arn <topic-arn> --protocol email --notification-endpoint you@example.com --region us-east-1
```
Then Console → **Billing → Budgets → Create budget** → *Cost budget* → monthly **$150**, with
alert thresholds at **$50 / $75 / $100 / $130** → notify the SNS topic / your email.
(Budgets metrics live in `us-east-1`.)

## 6. Run the backtest on EC2

```bash
# Launch a t3.medium in us-east-2 with the instance role attached, then:
git clone https://github.com/fede-giorgi/AI-Agent-Driven-Hedge-Fund.git
cd AI-Agent-Driven-Hedge-Fund
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Long run survives disconnects; per-day progress prints plain log lines.
tmux new -s bt
python -m backtesting.run_backtest \
  --start 2026-01-01 --end 2026-03-31 \
  --tickers AAPL,MSFT,NVDA,GOOGL,META \
  --capital 100000 --risk 6 --screen-top 5
# detach: Ctrl-b d   |   reattach: tmux attach -t bt
```
`python main.py --dev` routes to the same harness. **Stop the instance when idle** (compute also draws on the credit, though tokens dominate).

## 7. Cost reminders
- Non-reasoning mode (default) — a "thinking" run balloons output tokens at output-token price.
- Estimate: an optimized 1-analyst 3-month run ≈ **$22–28** on the tiered setup → ~5–6 runs on $150.
- Use `--screen-top` for large universes; the skip-gate + adaptive stop cut effective day-runs.
