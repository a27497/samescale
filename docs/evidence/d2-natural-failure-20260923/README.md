# D2 natural failure diagnosis — A/candidate/1

**D2 COMPLETE for this one historical natural failure.** This case was not manufactured from
the seeded Hook fixture. The chain is:

| Link | Source and observation |
| --- | --- |
| Real Run → Failure | [Original result](../l1-a-candidate-real-20260921/result.json): one `A/candidate/1` attempt; 600-second subject timeout, 601.037-second recorded duration, `harness_error`; original verifier `NOT_RUN` and Episode `NOT_VERIFIED`. |
| Saved workspace | [Five saved files](../l1-a-candidate-closeout-20260921/README.md) are digest-bound; [read-only snapshot audit](../l1-a-candidate-offline-audit-20260921/verify_snapshot.py) matches them to the 99-file output workspace. |
| Independent verification | [Later offline verifier report](../l1-a-candidate-offline-audit-20260921/verifier-evidence/report.json) has 71/75 checks; 4 A3 business assertions fail. Separate 12/22 supplemental component checks expose A4 private-use language defects. These are saved-workspace findings, not a formal original Episode score. |
| Scoped diagnosis | Repeated variants/extensions remain invalid; private-use language tags become `und` on both tested surfaces. **Workspace Contract defects are verified**. The original timeout remains a recorded evaluation boundary. Model capability and Harness root causes are **NOT_ESTABLISHED**. |
| Freeze | [D2 freeze](freeze.json) pins the original Episode/result, five-file mapping index, snapshot verifier code, 21-file audit index, audit result and verifier report. The previous immutable files were not modified. |
| Offline Replay ×2 | `scripts/replay_d2.py` checks the pins and reads the saved evidence as data, including the 21-file audit inventory and raw assertions; it never loads evidence Python as code. Two runs must match the frozen output digest `sha256:667f2a00d9bbccbffd02665ce40d2e4158dd0cc03b687b04baf11035928c4e57`. It runs no Agent, model, verifier or captured command. |
| CI Regression | `scripts/verify_s3_regression.py` runs the D2 replay twice inside the existing network-isolated Offline CI entry, checks both against the fixed digest, compares the two outputs and runs tamper/boundary tests. |
| Demo drill-down | The Recruiter Demo presents original timeout/NOT_VERIFIED, later 71/75, A3/A4 and attribution as distinct evidence layers. |

The post-timeout offline audit had an initial writable bind-mount failure and a supplemental
directory-permission failure; its records keep those environment faults separate from the
completed verifier findings. This D2 replay does not repeat those verifier attempts. The
original run's usage, Provider request status and timeout root cause remain unknown. The
historical L1 comparison remains inconclusive; D2 does not establish a Model/Harness ranking.
