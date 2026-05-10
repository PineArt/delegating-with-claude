## Step S1. Run-Specific Responsibility Matrix

Canonical Defaults: Apply

Phase-Critical Action | Owner Resolution | Required Record | Override? | Notes
S6 integration closure | Orchestrator | Integration Ledger and Decision Log | No | Main Codex thread integrates outputs.
S7 gate verdict | Quality Gate | Gate Decision | No | Independent gate agent will review final diff and validation.
S7 gate outcome append and replay coordination | Orchestrator | Decision Log and refreshed downstream artifacts | No | If gate requests rework, orchestrator updates artifacts.
Gate-requested rework | Implementer | refreshed artifact from Return Step | No | Dalton owns code/doc rework unless the gate narrows it to orchestration records.
Re-gate after corrective work | Quality Gate | fresh Gate Decision | No | Volta owns re-gate after rework evidence is available.
S8 publish readiness verification | Orchestrator | publish checklist and Decision Log | No | Final publish readiness remains with main thread.
S8 publish, commit, check-in, or submit | Orchestrator | Published Version, Decision Log, commit evidence when applicable | No | No alternate publish owner is assigned.
