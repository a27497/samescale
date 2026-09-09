# DeepSeek official Responses planning evidence — 2026-09-08

Sources checked 2026-09-08 (UTC):

- [Official models and pricing](https://api-docs.deepseek.com/quick_start/pricing/):
  deepseek-v4-flash, current version DeepSeek-V4-Flash-0731, context 1M tokens.
  Peak cache-miss input $0.44 / 1M tokens; peak output $1.32 / 1M tokens.
  Pricing is token-based; the user-selected request charge is $0.
- [Official Responses contract](https://api-docs.deepseek.com/api/create-response/):
  POST /responses supports deepseek-v4-flash and text.format type json_schema.
  max_output_tokens includes visible and reasoning output.

Conservative planning uses peak cache-miss rates for every input token regardless of
actual cache state/time. Context 1M is represented as 1,000,000 tokens. Prices can change;
the new dated profile price reference is an auditable planning snapshot, not a live
billing guarantee. Provider structured-output behavior is NOT_RUN / NOT_VERIFIED.
No frozen historical release/evidence file is modified by this reference.
