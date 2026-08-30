# References

Every calibration in `resiliency/` traces to an entry here; entries note
what they pin and their vintage. Verified against the primary URLs on
2026-08-29. Dollar figures in the policy ladder are planning-grade
assumptions, flagged as such in [docs/study.md](docs/study.md).

## Fiber: cut rates, repair times, single-access reality

**[1] Fiber-cut rates (the standard planning numbers — and their
vintage).** 4.39 cable cuts per 1,000 sheath-miles per year (Zhang &
Mukherjee, IEEE Network 2004); FCC-derived metro vs long-haul split: **13
cuts/yr per 1,000 route-miles metro, 3 long-haul** (Grover, *Mesh-Based
Survivable Networks*, 2004). These rest on 1990s–2000s US data recycled
through the optical literature — defensible for planning, dated as
measurement. Pins the `fiber.cut` rate (0.08/yr on a ~10 km access
route).
[Zhang & Mukherjee](https://dl.acm.org/doi/10.1109/MNET.2004.1276610) ·
[Coded Path Protection §I, refs [1][2]](https://arxiv.org/pdf/1112.4955)

**[2] Repair times and the single-access floor.** Buried-fiber repair
planning uses 8–14 h; enterprise DIA SLAs commit 4–8 h MTTR with
99.9%–99.99% availability; 99.9% is the common single-homed baseline and
measured availability typically sits at or below that floor (no carrier
publishes per-link measurements). An unprotected 1,200 km long-haul
wavelength ≈ 31 h expected downtime/yr. Pins `fiber` MTTRs and the
`upstream` mode calibrated to land P0's fiber at ~99.91%.
[MapYourTech, availability design](https://mapyourtech.com/optical-network-architecture-design-for-maximum-availability/) ·
[Lightyear, business internet SLAs](https://lightyear.ai/blogs/business-internet-sla) ·
[High-availability nines table](https://en.wikipedia.org/wiki/High_availability)

## Microwave

**[3] E-band engineering: rain degrades, adaptive modulation holds the
link.** Links engineered to 99.9–99.999% via ITU-R P.530/P.837 rain
models; E-band planning attenuation ~17 dB/km (99.99%) to ~31 dB/km
(99.999%); ADI shows 99.999% achievable on a 1 km E-band link at
100 mm/h rain. Modern capacity ~10 Gbps typical, 20 Gbps demonstrated.
Key modeling nuance pinned into `microwave.rain-fade`: rain mostly
*degrades capacity* (adaptive modulation), it does not drop the link.
[Analog Devices, E-band radio links](https://www.analog.com/en/resources/technical-articles/e-band-wireless-radio-links.html) ·
[Ericsson Microwave Outlook 2025](https://www.ericsson.com/en/reports-and-papers/microwave-outlook)

**[4] Microwave is half the world's backhaul.** Ericsson (Oct 2025):
global backhaul heading to a 49% microwave / 51% fiber split by 2030;
microwave in 75% of live 5G networks; E-band now 8% of deployments. The
fiber-first assumption behind "just get a second fiber" does not hold
for most of the world's sites.
[Ericsson Microwave Outlook 2025](https://www.ericsson.com/en/news/2025/10/microwave-outlook-2025-near-fiber-split-ai-and-2x-capacity)

## LEO satellite

**[5] Starlink: official spec vs measured behavior.** Spec: 25–60 ms
latency on land, 25–220 Mbps down / 5–20 Mbps up; **no jitter or
availability figure published**. Measured: Ookla 2025 US median ~118
Mbps down / ~17 up / ~45 ms; three independent studies replicate
globally synchronized **15-second path-reconfiguration intervals**
(reallocations at seconds 12/27/42/57) causing step changes in
latency/throughput. Pins `leo` RTT/capacity and the `flap` mode's
cadence framing.
[Starlink specifications](https://starlink.com/legal/documents/DOC-1723-29826-76) ·
[Multifaceted Look at Starlink (WWW '24)](https://arxiv.org/abs/2310.09242) ·
[Starlink one-way delay (LEO-NET '25)](https://dl.acm.org/doi/10.1145/3748749.3749090)

**[6] Starlink outage distribution: frequent, short, heavy-tailed.** A
2025 3-month measurement recorded thousands of outage events with ~80%
probability of at least one outage in any 60-minute window; durations
heavy-tailed; dish telemetry attributes causes (obstruction, no
downlink ~134 s, sky search ~221 s); many short outages align to the
15-s boundary. No study publishes a single clean availability
percentage — the honest model is many short flaps plus rare long tails,
which is what `leo.flap` (200/yr × ~72 s) + `leo.outage` (3/yr × 1.5 h)
encodes.
[Robust live streaming over LEO (2025)](https://arxiv.org/pdf/2508.13402) ·
[First look at Starlink performance (IMC '22)](https://dl.acm.org/doi/10.1145/3517745.3561416) ·
[Starlink vs 5G reliability (2025)](https://arxiv.org/pdf/2512.19639)

**[7] The rest of the LEO field.** OneWeb/Eutelsat (1,200 km, no ISLs):
independent measurement shows handover-driven latency bimodality
(~50 vs ~100 ms) against the marketed 70 ms; positioned for enterprise
backhaul (Telstra: 300+ remote base stations). Amazon Leo/Kuiper:
~11% of constellation launched mid-2026, beta late 2026/2027 — a future
entrant, not a modelable transport today.
[APNIC, measuring OneWeb](https://blog.apnic.net/2025/09/10/measuring-the-oneweb-satellite-network/) ·
[Kuiper availability tracker](https://orbitalradar.com/satellite-internet/kuiper-availability)

## Bonding & standards

**[8] Multi-WAN bonding is shipping engineering, not research.** Peplink
SpeedFusion: packet-level bonding, session-persistent hot failover, WAN
smoothing (duplication across links), FEC — explicitly for
Starlink+cellular designs. Cisco published a validated design (CVD) for
Starlink as a measured SD-WAN underlay (primary, backup, or
augmentation; up to 8 dishes). Ericsson Cradlepoint markets
Starlink-as-failover-WAN. Pins P3's mechanism: the model assumes bonded
policies absorb LEO flaps via duplication, which is exactly what these
products do.
[SpeedFusion](https://www.peplink.com/technology/speedfusion-bonding-technology/) ·
[Cisco SD-WAN Starlink CVD](https://www.cisco.com/c/en/us/td/docs/solutions/CVD/Campus/Cisco_SDWAN_Starlink_LEO_Satellite_CVD.html) ·
[Cradlepoint Starlink/5G](https://cradlepoint.com/solutions/starlink-5g-and-lte/)

**[9] The 3GPP basis: ATSSS + Rel-17 NTN/IAB.** ATSSS (Rel-16, TS
23.501 §5.32) standardizes multi-access PDU sessions with
steering/switching/splitting across 3GPP and non-3GPP access; Rel-17
adds autonomous steering, NR-NTN (transparent LEO/GEO payloads) and
enhanced IAB. Scope caution the marketing omits: Rel-16/17 ATSSS pairs
3GPP with *non-3GPP* access (e.g. Wi-Fi); dual-3GPP ATSSS was a Rel-19
discussion item; NTN and ATSSS are complementary work items, not one
integrated feature.
[3GPP Release 17](https://www.3gpp.org/specifications-technologies/releases/release-17) ·
[Enhanced ATSSS (arXiv:2302.05439)](https://arxiv.org/pdf/2302.05439)

## Power — the dominant failure mode

**[10] FCC disaster record: cell outages are power outages.** FCC 21-99:
>50% of cell-site outages in major 2020 disasters were power failures.
Hurricane Ida (2021): 52% of sites down in the worst-hit parishes.
Hurricane Helene (2024): record 4,562 sites down, 66.4% out in affected
NC counties. Widely misquoted caveat: the FCC's 2007 order seeking 8 h
minimum backup at cell sites **never took effect** (vacated after
challenges) — there is no federal backup-power mandate. Pins the storm
process (`StormConfig`) and `grid_outage_p=0.7`.
[FCC 21-99 (PDF)](https://docs.fcc.gov/public/attachments/FCC-21-99A1.pdf) ·
[FCC DIRS, Helene](https://docs.fcc.gov/public/attachments/DOC-405943A1.pdf) ·
[FCC DIRS, Ida](https://docs.fcc.gov/public/attachments/DOC-375318A1.pdf)

**[11] Battery and generator envelopes.** Typical cell-site batteries
last 2–8 h (industry practice; regulatory expectations for critical
sites 8–24 h); ~78% of macro sites carry permanent generators with
72–120 h per fuel tank (CA post-PSPS commitments). Pins
`PowerConfig(battery_h, generator_fuel_h)` and the P4 generator rung.
[FCC 21-99](https://docs.fcc.gov/public/attachments/FCC-21-99A1.pdf) ·
[Wireless Estimator, Helene analysis](https://wirelessestimator.com/articles/2024/unprecedented-outage-no-hurricane-has-knocked-out-more-cell-sites-than-category-4-helene/)

**[12] Grid baseline (EIA, primary).** 2024 US average ~11 h of
interruption per customer-year including major events (~9 h from major
events, ~2 h routine ≈ 99.977% grid availability); decade average ~6 h.
2024's hurricanes alone were 80% of outage hours. Pins
`routine_outages_per_year × routine_outage_h` and validates
storm-dominance. Cell-site repair MTTR beyond the grid (2–24 h truck
roll) has **no public primary source** — labeled an assumption.
[EIA, Today in Energy (2025-12-01)](https://www.eia.gov/todayinenergy/detail.php?id=66744)

## Timing

**[13] GNSS holdover: OCXO hours, rubidium days.** Microsemi (primary
vendor doc): rubidium holdover keeps phase within 400 ns over 24 h
(recommended budgets 250 ns/16 h → 750 ns/36 h) — comfortably inside
the 3GPP ±1.5 µs cell budget for 24 h+. OCXO class drifts ~1–10 µs over
24 h → the ±1.5 µs budget holds roughly 4–15 h by grade. Jamming is a
growth industry: >430,000 GNSS interference incidents in 2024; IATA
reports jamming +67% and spoofing +193% (2024→2025). Pins
`TimingConfig.holdover_h` (6 h OCXO / 36 h rubidium).
[Microsemi, rubidium holdover for PTP (PDF)](https://syncworks.com/wp-content/uploads/2023/06/Microsemi_Rubidium_Holdover_for_PTP_Phase_Synchronization_Applications_A.pdf) ·
[OCXO vs rubidium holdover](https://timebeat.app/learn/ocxo-vs-rubidium-holdover) ·
[FAA/IATA jamming surge](https://www.globalair.com/articles/faa-flags-global-surge-in-gps-jamming-and-spoofing-updates-its-playbook/12178)

## WAN failure structure

**[14] Hyperscaler WAN failure data.** Google "Evolve or Die" (SIGCOMM
'16): 100+ high-impact events; **80% of failures last 10–100 minutes**;
many coincide with management operations. Microsoft (IMC '16): a year of
optical-backbone data shows link availabilities vary widely —
equal-failure-probability assumptions are wrong. Supports the modeling
choice of heterogeneous per-mode rates over a single availability
number.
[Evolve or Die (PDF)](https://people.eecs.berkeley.edu/~sylvia/cs268-2019/papers/ramesh16a.pdf) ·
[Optical layer failures (IMC '16)](https://www.microsoft.com/en-us/research/publication/optical-layer-failures-large-backbone-2/)

## The blueprint side (Deliverable 1 sources)

**[15] O-RAN fronthaul & timing budgets.** ~100 µs one-way O-DU↔O-RU
budget (WG4 delay management); PTP G.8275.1 (02/2026 edition); ±1.5 µs
end-to-end per G.8271.1; O-RAN WG11 makes MACsec *optional* on open
fronthaul planes and adopts NIST zero-trust tenets. Why R0 rides only
fiber/E-band in `classes.py`.
[ITU-T G.8275.1 (2026-02)](https://www.itu.int/rec/T-REC-G.8275.1-202602-I) ·
[O-RAN security update 2025](https://www.o-ran.org/blog/o-ran-alliance-security-update-2025)

**[16] Carrier control plane: SRv6 + BGP-EVPN mature; intent-routing
younger.** RFC 8986 (2021), RFC 9252 (2022) Standards Track; EANTC 2025
interop: 9/9 SRv6 vendors support µSID, EVPN-over-SRv6 tested, 5G
x-haul slicing validated. TI-LFA (RFC 9855): sub-50 ms protection is a
vendor design target (Cisco docs), not an interop measurement. BGP CAR
(RFC 9871) and BGP CT (RFC 9832) landed 2025 as **Experimental**.
DetNet (RFC 8655) explicitly scopes itself to single-administration
domains — not the open internet.
[RFC 8986](https://www.rfc-editor.org/info/rfc8986) ·
[RFC 9252](https://www.rfc-editor.org/info/rfc9252) ·
[EANTC 2025](https://wiki.eantc.de/wiki/publicreports/view/Main/Multi-Vendor%20MPLS%20%26%20SDN%20Interoperability%20Test%20Report%202025/SRv6) ·
[RFC 8655](https://www.rfc-editor.org/rfc/rfc8655.html)

**[17] Zero-trust multi-tenancy is DPU-enforced, host-excluded.** NVIDIA
DPF Zero-Trust reference: host sees the DPU as a plain NIC, management
via DPU BMC out-of-band. Netris v4.7 (Apr 2026): BlueField zero-trust
via DOCA with per-tenant isolation down to a single GPU. CoreWeave runs
this in production: EVPN Type-5 into per-tenant VRFs/VXLAN on
BlueField-3 ("Nimbus") isolated from the host. BlueField-4 (announced
GTC Washington, Oct 28, 2025): 800 Gb/s, Grace + ConnectX-9, shipping
with Vera Rubin platforms in 2026.
[NVIDIA DPF Zero Trust RDG](https://networking-docs.nvidia.com/sol/rdg-for-dpf-zero-trust-(dpf-zt)-with-argus-dpu-service) ·
[Netris + BlueField](https://www.businesswire.com/news/home/20260423579798/en/Netris-Extends-AI-Network-Automation-and-Multi-Tenancy-to-NVIDIA-BlueField-DPUs) ·
[CoreWeave security architecture](https://docs.coreweave.com/docs/security/architecture) ·
[NVIDIA BlueField-4](https://blogs.nvidia.com/blog/bluefield-4-ai-factory/)

**[18] What neoclouds actually promise.** CoreWeave's only public
numeric uptime SLA is 99.9% — for AI Object Storage; GPU-compute
guarantees (~99% rack-level with penalties) are negotiated contract
terms per SemiAnalysis, not published SLAs. ClusterMAX 2.0 (Nov 2025):
CoreWeave sole Platinum; lower tiers documented shipping clusters with
GPUDirect RDMA disabled or PCIe ACS on. Carrier-grade language and
neocloud reality are far apart — which is the gap this repo prices.
[CoreWeave object-storage SLA](https://docs.coreweave.com/docs/policies/terms-of-service/coreweave-ai-object-storage-policy) ·
[ClusterMAX 2.0](https://newsletter.semianalysis.com/p/clustermax-20-the-industry-standard)

**[19] RAN floor on shared GPUs.** NVIDIA Aerial validates RAN on a
pinned MIG slice with LLM tenancy alongside (up to 11 cells in the
4g.48g + 3g.48gb layout); documented active-standby fronthaul port
failover and L1 recovery behavior. MIG reconfiguration requires idle
instances — the RAN floor is static, not preemptible.
[Aerial 25-2 release notes](https://docs.nvidia.com/aerial/cuda-accelerated-ran/25-2/aerial_cubb/release_notes/limitations.html) ·
[Aerial fronthaul failover](https://docs.nvidia.com/aerial/cuda-accelerated-ran/25-1/aerial_cubb/cubb_quickstart/active-standby.html) ·
[MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/concepts.html)

## Cost assumptions (planning-grade, not quotes)

**[20]** Monthly figures in `transports.py`/`site.py` — 10G DIA $1,500,
licensed E-band link $800 (amortized), business LEO $250, 5G FWA $150,
genset $400 (amortized + fuel service), battery $40 per bridge-hour,
rubidium $60 — are planning-scale estimates consistent with published
DIA/SLA guides [2] and business-service list prices. They set the
*ordering* of the cost axis, not procurement truth; every one is a
constructor argument.
