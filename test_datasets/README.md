# Side-Scan Sonar Standard Testing Dataset Suite (V4.2)

Curated benchmark dataset for evaluating multi-model Side-Scan Sonar AI models.
Organized into 4 distinct contact categories to validate model accuracy, suppress false clean-seabed classifications, and verify bounding reticles.

---

## Directory Overview

| Folder | Files | Primary Ground Truth | Recommended Model | Optimal Conf |
|---|---|---|---|---|
| `01_naval_mines/` | 23 | Real Naval Sea Mines (MILCO / NOMBO) | `mines` / `shipwreck` | `0.16` - `0.20` |
| `02_shipwrecks/` | 22 | Sunken Wooden & Steel Vessel Hulls | `shipwreck` | `0.16` |
| `03_cylinders_and_containers/` | 3 | Industrial Cylinders, Oil Drums, Fuselage | `cylinder` | `0.25` |
| `04_clean_natural_seabed/` | 25 | Pristine Seabed (Sand, Mud, Gravel, Rock) | `natural_seabed` | `0.50` |

---

## How to Test Each Category

### 1. Naval Mines (`01_naval_mines/`)
- **Acoustic Signature:** Sharp, high-contrast specular acoustic highlight followed by a distinct acoustic shadow.
- **Model to Select:** Select **Mine Detector (`mines`)** or **All Models**.
- **Confidence Cutoff:** `0.16` - `0.20` (naval mine contacts are compact, occupying 0.5% - 2% of swath).
- **Expected Result:** High-confidence bounding reticle tagged as `MILCO (Mine-Like Contact)` or `NOMBO (Non-Mine Bottom Object)`.

### 2. Shipwrecks (`02_shipwrecks/`)
- **Acoustic Signature:** Elongated structural backscatter with ribs, keels, or superstructure shadows.
- **Model to Select:** Select **Shipwreck Detector (`shipwreck`)**.
- **Confidence Cutoff:** `0.16`.
- **Expected Result:** Reticle encompassing the wreck perimeter tagged as `Shipwreck / Maritime Wreck`.

### 3. Industrial Cylinders (`03_cylinders_and_containers/`)
- **Acoustic Signature:** Linear or rounded specular echo with uniform elongated shadow.
- **Model to Select:** Select **Cylinder Detector (`cylinder`)**.
- **Confidence Cutoff:** `0.25` - `0.35`.
- **Expected Result:** Reticle tagged as `Industrial Cylinder / Drum`.

### 4. Clean Natural Seabed (`04_clean_natural_seabed/`)
- **Acoustic Signature:** Uniform seafloor sediment texture (sand ripples, flat mud, gravel field). Zero man-made debris.
- **Model to Select:** Select **Natural Seabed Classifier (`natural_seabed`)**.
- **Expected Result:** Certified clean seabed with P(clean) >= 95%, zero false alarm bounding boxes.
