# 模擬配置參考

## Cauer 2-Node RC Thermal Parameters

| 參數 | 符號 | 數值 | 單位 | 物理意義 |
|---|---|---|---|---|
| Die-to-package resistance | R₁ | 5.0 | K/W | Junction → package case |
| Package-to-ambient resistance | R₂ | 10.0 | K/W | Package → ambient air |
| Die thermal capacitance | C₁ | 1.0 | J/K | Silicon die heat storage |
| Package thermal capacitance | C₂ | 5.0 | J/K | Package/lid heat storage |
| Ambient temperature | T_amb | 25.0 | °C | Fixed reference |

**Derived values:**
- `tau_die = C₁ × R₁ = 5.0 s`
- `tau_pkg = C₂ × (R₁ + R₂) = 75.0 s`
- `R_total = R₁ + R₂ = 15.0 K/W`
- `T_steady (3W) = 25 + 3×15 = 70.0°C`

## gem5 OPP（Operating Performance Points）

### Big core（Cortex-X4 class）
| Freq (GHz) | Voltage (V) | P_dynamic (approx W) |
|---|---|---|
| 3.3 | 1.20 | 2.5–4.0 (IPC dependent) |
| 3.0 | 1.10 | 1.8–3.0 |
| 2.8 | 1.05 | 1.5–2.5 |
| 2.4 | 0.95 | 1.0–1.8 |
| 2.0 | 0.85 | 0.6–1.2 |

### Little core（Cortex-A520 class）
| Freq (GHz) | Voltage (V) |
|---|---|---|
| 2.0 | 0.85 |
| 1.5 | 0.75 |
| 1.0 | 0.65 |

## gem5 Power Model

```python
P_dynamic = V^2 * 3.0 * IPC
P_leak    = 0.1 * (T_temp / 300)^2
```

## Phase-specific stats-period choices

| Phase | --stats-period | 理由 |
|---|---|---|
| Phase 5（bug discovery） | 0.0002 s (0.2 ms) | 捕捉第一個 thermal step anomaly |
| Phase 5.5（validation） | 0.0002 s | 和 Phase 5 保持一致，便於比較 |
| Phase 6（EAS） | 0.005 s (5 ms) | EAS 決策約每 4ms 發生，檔案也會小很多 |
