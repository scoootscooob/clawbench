# ClawBench 7-Model Frontier Bake-off — Results Summary

All seven profiles share an identical plugin stack
(`anthropic` + `memory-lancedb` + `browser-playwright`)
so the base model is the only structural variable.

## Headline

| Metric | Claude Opus 4.6 (closed) | GPT-5.4 (closed) | Gemini 3.1 Pro (closed) | GLM-5.1 (open) | Qwen3.6-Plus (open) | MiniMax M2.7 (open) | Kimi K2.5 (open) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Overall score | 0.639 | 0.408 | 0.405 | 0.403 | 0.338 | 0.416 | 0.383 |
| Completion | 0.444 | 0.111 | 0.111 | 0.111 | 0.111 | 0.111 | 0.222 |
| Trajectory | 0.719 | 0.479 | 0.470 | 0.462 | 0.247 | 0.507 | 0.247 |
| Behavior | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Reliability | 0.467 | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 | 0.200 |
| Cost / pass | $0.1824 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 | $0.0000 |

## Sources

- **Claude Opus 4.6** (closed): `results/frontier_opus_4_6.json`
- **GPT-5.4** (closed): `results/frontier_gpt_5_4.json`
- **Gemini 3.1 Pro** (closed): `results/frontier_gemini_3_pro.json`
- **GLM-5.1** (open): `results/frontier_glm_5_1.json`
- **Qwen3.6-Plus** (open): `results/frontier_qwen_3_6.json`
- **MiniMax M2.7** (open): `results/frontier_minimax_m27.json`
- **Kimi K2.5** (open): `results/frontier_kimi_k25.json`
