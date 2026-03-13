# Turkish LLM Benchmark Results
_Güncellendi: 2026-03-13T23:33:20+03:00_

## Model Karşılaştırma
| Model | Accuracy % | Success/Scored | Median | Mean | P95 | Latency Score |
|---|---:|---:|---:|---:|---:|---:|
| qwen3.5:397b | 100.0 | 4/4 | 17.07s | 16.80s | 21.08s | 15.2 |
| gemma3:12b | 87.5 | 7/8 | 2.60s | 3.62s | 7.77s | 100.0 |
| gemma3:4b | 77.8 | 7/9 | 3.43s | 3.56s | 4.96s | 75.9 |
| gemma3:27b | 66.7 | 2/3 | 6.80s | 7.60s | 10.48s | 38.2 |

## Soru Bazlı Sonuç Matrisi
| Soru ID | Kategori | gemma3:12b | gemma3:27b | gemma3:4b | qwen3.5:397b |
|---|---|---|---|---|---|
| q001 | Türkçe | ✅ 2.65s | - | ✅ 3.43s | - |
| q002 | Türkçe | ✅ 2.36s | - | ✅ 3.12s | - |
| q003 | Türkçe | ✅ 2.55s | - | ✅ 3.46s | - |
| q004 | Türkçe | ✅ 2.52s | - | ✅ 3.25s | - |
| q005 | Türkçe | - | - | - | - |
| q006 | Türkçe | - | - | - | - |
| q007 | Mantık | ❌ 9.44s | ✅ 10.89s | - | - |
| q008 | Mantık | - | - | ✅ 3.83s | - |
| q009 | Mantık | - | - | - | - |
| q010 | Mantık | - | - | - | - |
| q011 | Tarih | - | - | - | - |
| q012 | Coğrafya | - | - | - | - |
| q013 | Genel Kültür | - | ❌ 5.11s | ❌ 3.02s | ✅ 19.04s |
| q014 | Genel Kültür | - | - | - | ✅ 21.44s |
| q015 | Genel Kültür | - | - | - | - |
| q016 | Genel Kültür | ✅ 2.92s | ✅ 6.80s | ✅ 3.58s | ✅ 11.60s |
| q017 | FİNANS | - | - | - | - |
| q018 | FİNANS | - | - | - | - |
| q019 | KODLAMA | - | - | - | - |
| q020 | HAFIZA | ✅ 1.87s | - | ❌ 2.65s | - |
| q021 | HAFIZA | ✅ 4.68s | - | ✅ 5.72s | ✅ 15.10s |
| q022 | HAFIZA | - | - | - | - |
| q023 | HAFIZA | - | - | - | - |
