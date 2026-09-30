# Tailnet-only QA closeout — 2026-09-30

The earlier authorized QA proxy remained restricted to the Tailnet; no public Funnel was enabled.
[Original Tailnet gate projection](gate-public.json): **12/12 PASS**.
[Read-only checks](read-only-public.json): public mutations returned **403 PUBLIC_DEMO_READ_ONLY**,
with original Demo identity/digest unchanged. Host firewall, gateway/certificate and application
configuration were unchanged during targeted UAT. Raw addressing/configuration receipts are
privately archived; public projections retain their original SHA256 references.

[Latest Grok targeted UAT](../uat-closeout-20260930/grok-targeted-uat.json) supplied by the user:
**PASS**, all six findings closed, **NEW REGRESSION=NONE**. Tailnet QA is verified for this
internal acceptance. The earlier client-access pending state is superseded by this result.
**Public internet / trusted TLS remain NOT_VERIFIED**. No deployment or network change in Git closeout.
