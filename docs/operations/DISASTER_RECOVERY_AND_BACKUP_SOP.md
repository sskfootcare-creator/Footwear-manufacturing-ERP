# Standard Operating Procedure: Database Backup & Disaster Recovery (DATA-025)

**Document Reference:** SOP-OPS-025  
**Audit Reference:** DATA-025, ARCH-001  
**Target Audience:** DevOps, On-Call Engineers, Database Administrators  

---

## 1. RPO and RTO Targets

| Target Metric | Approved Standard | Implementation Mechanism |
| :--- | :--- | :--- |
| **RPO (Recovery Point Objective)** | **<= 1 hour** (MongoDB) / **<= 15 min** (Supabase) | Hourly incremental snapshots; Supabase WAL Continuous Archiving (PITR) |
| **RTO (Recovery Time Objective)** | **<= 2 hours** | Automated restore script `scripts/db_backup_restore.py`; IaC deployment via Docker/K8s |

---

## 2. Backup Schedule & Retention Policy
1. **Daily Operational Snapshots**: Run at 02:00 UTC daily via cron/workflow.
2. **Retention Schedule**:
   - Daily backups: Retained for 7 days.
   - Weekly full backups: Retained for 4 weeks.
   - Monthly archived snapshots: Retained for 12 months in cold object storage (`S3 Glacier`).
3. **Encryption at Rest**: All exported archives are encrypted with AES-256 before transfer to S3.

---

## 3. Scheduled Restore Drills
- Disaster recovery restore drills are executed quarterly in a segregated staging environment (`ssk_restore_drill_db`).
- Script: `python scripts/db_backup_restore.py`
- Drill validation verifies:
  1. Complete extraction of all collections.
  2. BSON/JSON deserialization without corruption.
  3. Re-indexing and index integrity validation.
  4. Cross-reconciliation check against Supabase financial core.
