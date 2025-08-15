# ThreatAtlas Whitepaper

## Abstract
ThreatAtlas is a modular cyber risk assessment and scoring framework designed to evaluate and rank countries based on their overall cyber threat posture. The system ingests multiple datasets, applies configurable scoring logic, and produces a unified "Risk Score" that reflects the geopolitical and cyber threat landscape. The latest iteration introduces a cross-platform GUI for both technical and non-technical users, allowing data filtering, search, and exclusion functionality without requiring command-line interaction.

---

## 1. Introduction
Cyber threats have evolved into a global concern affecting governments, corporations, and individuals. Nation-states, cybercriminal organizations, and hacktivist groups increasingly operate across borders, creating a need for a comprehensive, data-driven assessment of country-level cyber risks.

ThreatAtlas addresses this need by combining open-source intelligence (OSINT) with a flexible scoring algorithm to generate an actionable **Risk Score** for each country. These scores assist in threat modeling, geopolitical analysis, and cyber defense planning.

---

## 2. System Overview
ThreatAtlas operates in two primary modes:
1. **Command-Line Interface (CLI)** – For automation, integration into larger pipelines, and batch analysis.
2. **Graphical User Interface (GUI)** – For interactive exploration, filtering, and reporting.

Key Features:
- **Multi-source data ingestion** (custom CSVs, aliases, and supplemental datasets).
- **Dynamic scoring engine** with configurable weightings.
- **Filtering options** for country inclusion/exclusion.
- **Search functionality** for targeted queries.
- **Standalone or integrated operation**.
- **Exportable results** for integration into intelligence workflows.

---

## 3. Architecture
ThreatAtlas is built as a modular Python application:
- **Core Engine (`controller.py`)** – Orchestrates data ingestion, scoring, and output.
- **Data Modules** – Parse and preprocess CSVs and other input formats.
- **GUI Layer (`gui_main.py`, `gui/`)** – Built with Tkinter for portability without requiring a browser or open network port.
- **Configurable Pipeline** – Supports both default and custom scoring rules.

---

## 4. Scoring Algorithm
The ThreatAtlas scoring algorithm is designed to merge multiple threat intelligence datasets into a single, comparable **Risk Score** for each country.  

### 4.1 Input Data Sources
The default scoring algorithm uses:
- **Global Cybersecurity Index (GCI)** – Inverted so that lower rankings (weaker cybersecurity) result in higher risk contribution.
- **National Cyber Security Index (NCSI)** – Directly contributes to cyber defense capability weighting.
- **Spamhaus Spam Magnitude** – Measures outbound spam activity from the country as a proxy for botnet and malicious infrastructure presence.
- **Exploit Prevalence** – Tracks known exploit activity originating from the country.
- **Other OSINT Indicators** – Vulnerability counts, darknet activity, phishing prevalence, and geopolitical stability.

### 4.2 Normalization
Each dataset is normalized to a **0–1 scale**:  
`normalized_value = (value - min_value) / (max_value - min_value)`

For inverse indicators (where a higher raw value means less risk, e.g., GCI rank), the score is inverted:  
`normalized_value = 1 - normalized_value`

### 4.3 Weighting
Each normalized metric is multiplied by a weight factor:  
`Weighted Metric = Normalized Value × Weight`

Default weights:
- GCI Score: 0.25  
- NCSI Score: 0.25  
- Spam Magnitude: 0.20  
- Exploit Activity: 0.15  
- Vulnerability Exposure: 0.15  

### 4.4 Aggregation
The **Risk Score** is the sum of all weighted metrics, scaled to a 0–100 range:  
`Risk_Score = (Σ Weighted_Metrics) × 100`

### 4.5 Interpretation
- **80–100:** Extreme Risk  
- **60–79:** High Risk  
- **40–59:** Medium Risk  
- **20–39:** Low Risk  
- **0–19:** Minimal Risk  

### 4.6 Role of TOPSIS in ThreatAtlas

ThreatAtlas uses a hybrid scoring approach that combines its own weighted risk computation with the **Technique for Order of Preference by Similarity to Ideal Solution (TOPSIS)** method to ensure balanced, comparative ranking of countries.

**TOPSIS Overview:**
TOPSIS is a multi-criteria decision-making algorithm that ranks alternatives (in this case, countries) based on their relative distance to two ideal points:
- **Ideal Best (Positive Ideal Solution)** – The hypothetical scenario with the best values for all criteria (lowest risk).
- **Ideal Worst (Negative Ideal Solution)** – The hypothetical scenario with the worst values for all criteria (highest risk).

The core steps of TOPSIS:
1. **Construct the decision matrix** from normalized metrics.
2. **Apply weighting factors** to reflect the importance of each metric.
3. **Identify the positive and negative ideal solutions**.
4. **Calculate the Euclidean distance** of each country to both the positive and negative ideal solutions.
5. **Compute the relative closeness score**:  
   `Closeness = Distance_to_Worst / (Distance_to_Best + Distance_to_Worst)`
6. Rank countries by their closeness score (closer to 1 means lower risk, closer to 0 means higher risk).

**Integration with ThreatAtlas:**
- ThreatAtlas first **normalizes and weights** all input metrics using its internal functions.
- The weighted matrix is then **fed into the TOPSIS engine**, which ranks the countries based on proximity to the ideal low-risk profile.
- The raw TOPSIS output is **inverted and scaled** to the 0–100 Risk Score range, aligning it with ThreatAtlas's interpretation where higher scores represent higher risk.
- The resulting score reflects **both the relative position** of a country compared to others and the **absolute weight** of high-risk indicators.

**Advantages of this Hybrid Approach:**
- Maintains **relative ranking fairness** (TOPSIS) while preserving **absolute risk signal strength** (ThreatAtlas weights).
- Handles **multi-dimensional, heterogeneous data** effectively.
- Produces scores that are **both explainable and comparable** across multiple datasets and timeframes.

---

## 5. GUI Features
- **Run Scoring** directly from the GUI without CLI commands.
- **Country Inclusion/Exclusion Lists** for tailored analysis.
- **Data File Selection** for base CSVs, aliases, and supplemental datasets.
- **Search Functionality** for single or multiple countries.
- **Exportable Results** in CSV format.

---

## 6. Conclusion
ThreatAtlas bridges the gap between raw threat intelligence data and actionable national cyber risk assessments. Its modular architecture and configurable scoring system make it a valuable tool for cybersecurity analysts, researchers, and policymakers.

---

## 7. License
Licensed under the **Apache 2.0 License** – see LICENSE file for details.
