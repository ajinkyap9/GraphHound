# Seed Paths — Deliberately Configured Vulnerable Chains

This document records the attack chains that were deliberately seeded in the
lab environment (or present in the sample data) as ground truth.  The model
evaluation checks whether these paths rank in the **top 20 %** of the model's
output — if they do, the feature design is validated.

---

## Chains Present in `data/sample_bloodhound.json`

### Chain 1 — ACL Abuse → Group Escalation → Domain Admins

```
j.doe  ─MemberOf→  Helpdesk  ─GenericAll→  svc.backup  ─AddMember→  Tier0 Maintenance  ─MemberOf→  DOMAIN ADMINS
```

**Why it's high-risk:** GenericAll grants full control over `svc.backup`,
enabling password reset and Kerberoasting.  `AddMember` on `Tier0 Maintenance`
is a direct escalation to Domain Admins via group nesting.  The chain is short
(4 hops), uses high-impact edges, and the techniques (T1098) are highly
prevalent in real-world incidents.

### Chain 2 — RDP + Session Theft → DCSync

```
j.doe  ─CanRDP→  SQL01  ─HasSession→  svc.sql  ─GenericWrite→  Server Operators  ─AdminTo→  DC01  ─DCSync→  corp.local
```

**Why it's high-risk:** Starts from a common RDP entry point, pivots through
a service account session, escalates via GenericWrite, and culminates in
DCSync — the highest-impact technique (impact=1.0).  Although DCSync is noisy,
the path is fully realistic and leads to full domain compromise.

### Chain 3 — Short DCSync via Service Account

```
j.doe  ─MemberOf→  Helpdesk  ─GenericAll→  svc.backup  ─DCSync→  corp.local
```

**Why it's high-risk:** Only 3 hops.  GenericAll + DCSync is one of the most
critical real-world attack patterns.  This should rank near the very top.

---

## Chains to Seed in Your Lab AD (Template)

> **Instructions:** After you configure these chains in your lab, fill in
> the details below and re-export BloodHound JSON to
> `data/lab_bloodhound.json`.

### Lab Chain 1

```
[start user]  ─[edge type]→  [intermediate]  ─[edge type]→  ...  →  [target]
```

**Misconfiguration set up:**  
**Why it should rank highly:**  

### Lab Chain 2

```
[start user]  ─[edge type]→  [intermediate]  ─[edge type]→  ...  →  [target]
```

**Misconfiguration set up:**  
**Why it should rank highly:**  

### Lab Chain 3

```
[start user]  ─[edge type]→  [intermediate]  ─[edge type]→  ...  →  [target]
```

**Misconfiguration set up:**  
**Why it should rank highly:**  
