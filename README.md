# ThreatAtlas

ThreatAtlas is a modular cyber risk scoring framework that evaluates and ranks countries based on their overall cyber threat posture. It supports both **command-line** and **graphical user interface (GUI)** modes, enabling flexibility for analysts, researchers, and security teams.

---

## Features
- **Global Risk Scoring** – Calculates a composite "Risk Score" for each country.
- **Multiple Interfaces** – CLI for automation, GUI for interactive use.
- **Dynamic Filtering** – Include/exclude countries in analysis.
- **Search Functionality** – Find specific countries quickly.
- **Configurable Data Sources** – Load custom datasets and alias mappings.
- **Exportable Output** – Use results in other tools or reports.

---

## Scoring Algorithm

### Algorithm Overview — Combining TOPSIS with Custom Risk Computation

ThreatAtlas uses a hybrid scoring methodology that blends the **Technique for Order Preference by Similarity to Ideal Solution (TOPSIS)** with domain-specific weighting and scoring rules.

**TOPSIS** is a multi-criteria decision-making method that ranks entities by comparing their distance from an ideal “best” point and a worst-case “negative ideal” point. In ThreatAtlas:

1. Each risk metric (e.g., NCSI score, spam magnitude, exploit rank, GCI score, APT activity) is normalized to make values comparable.  
2. Positive indicators (e.g., higher security index) are treated inversely from negative indicators (e.g., malicious IP counts).  
3. Weighted factors are applied to reflect the real-world importance of each metric.  
4. For each country, the algorithm calculates its **closeness coefficient**—a score between 0 and 1 showing how close it is to the ideal point.  

ThreatAtlas then **augments TOPSIS** with custom computations to adjust rankings based on additional cyber threat intelligence patterns, trends, and categorical severity thresholds, producing a final **Risk_Score** and **Risk_Level** classification.


### Input Data Sources
By default, ThreatAtlas calculates **Risk Scores** using:
- **Global Cybersecurity Index (GCI)** – Inverted so weaker scores mean higher risk.
- **National Cyber Security Index (NCSI)** – Measures cyber readiness.
- **Spamhaus Spam Magnitude** – Proxy for botnet/malware infrastructure.
- **Exploit Activity** – Frequency of known exploits from the country.
- **Vulnerability Exposure** – Number of high-risk CVEs associated with IP ranges.

### Normalization
All metrics are normalized to a 0–1 scale:  
`normalized_value = (value - min_value) / (max_value - min_value)`

For inverse metrics:  
`normalized_value = 1 - normalized_value`

### Weighting
Each metric is multiplied by a default weight:  
- GCI: 0.25  
- NCSI: 0.25  
- Spam Magnitude: 0.20  
- Exploit Activity: 0.15  
- Vulnerability Exposure: 0.15  

### Aggregation
The Risk Score is:  
`Risk_Score = (Σ Weighted_Metrics) × 100`

**Score Ranges:**
- 80–100: Extreme Risk  
- 60–79: High Risk  
- 40–59: Medium Risk  
- 20–39: Low Risk  
- 0–19: Minimal Risk  

---

## Installation
```bash
git clone https://github.com/yourusername/ThreatAtlas.git
cd ThreatAtlas
pip install -r requirements.txt
pip install jsonschema==2.6.0
