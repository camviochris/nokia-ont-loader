import re
from datetime import datetime

import pandas as pd
import streamlit as st


st.set_page_config(page_title="📦 Inventory CSV Builder", layout="centered")
st.title("📦 Inventory CSV Builder")

st.markdown(
    "Upload one or more CSVs.\n\n"
    "- If a file includes a **model** column (recommended), the app will automatically set **device_name** and **device_profile**.\n"
    "- If a file does **not** include model, the app will use the manual fallback (device name + profile selectors).\n"
    "- You only choose **inventory_location**.\n"
    "- Output **inventory_status** is always **UNASSIGNED**.\n"
)

# --- Company name (used in output filename) ---
company_name = st.text_input(
    "Company name (used in output file name)",
    placeholder="e.g., AcmeFiber"
).strip()

# -------------------------------------------------------------------
# ✅ AUTHORITATIVE MAPPING (EDIT HERE WHEN NEW MODELS APPEAR)
#
# HOW TO ADD NEW MODELS (2 cases):
#
# Case A) The uploaded CSV model value EXACTLY matches the desired device_name
#   1) Add the device_name to DEVICE_PROFILE_BY_DEVICE_NAME with the correct profile.
#      Example:
#        DEVICE_PROFILE_BY_DEVICE_NAME["XS-999X-A"] = "NOKIA_ONT"
#
# Case B) The uploaded CSV model value is DIFFERENT than the desired device_name
#   (examples: extra words, different punctuation, vendor naming)
#   1) Ensure the canonical device_name exists in DEVICE_PROFILE_BY_DEVICE_NAME
#   2) Add an alias line in MODEL_ALIASES_TO_DEVICE_NAME mapping the exact model text
#      (lower/upper doesn't matter) to the canonical device_name.
#      Example:
#        MODEL_ALIASES_TO_DEVICE_NAME["Beacon G6 WiFi6"] = "Beacon G6"
#
# WHERE TO PUT IT:
#   - Add canonical device_names in DEVICE_PROFILE_BY_DEVICE_NAME
#   - Add model string variants in MODEL_ALIASES_TO_DEVICE_NAME
# -------------------------------------------------------------------
DEVICE_PROFILE_BY_DEVICE_NAME = {
    # Nokia Mesh
    "Beacon G6": "NOKIA_MESH",     # <-- IMPORTANT: Beacon G6 is NOKIA_MESH
    "Beacon 6": "NOKIA_MESH",
    "EMA-Beacon 2": "NOKIA_MESH",

    # Nokia ONT (extend as needed)
    "XS-110G-A": "NOKIA_ONT",
    "XS-230X-A": "NOKIA_ONT",
    "XS-220X-A": "NOKIA_ONT",
    "XS-2426X-A": "NOKIA_ONT",

    # VoIP / ATA
    "GS-HT802": "VOIP_PHONE_ADAP",

    # General
    "CUST-OWNED-GATEWAY": "GEN_DEVICE",
}

# Model aliases -> canonical device_name
# Add here when the uploaded CSV's model strings aren't exact matches.
MODEL_ALIASES_TO_DEVICE_NAME = {
    # Beacon G6 variations
    "beacong6": "Beacon G6",
    "beacon-g6": "Beacon G6",
    "beacon g6": "Beacon G6",

    # Beacon 6 variations
    "beacon6": "Beacon 6",
    "beacon-6": "Beacon 6",
    "beacon 6": "Beacon 6",

    # EMA-Beacon 2 variations
    "emabeacon2": "EMA-Beacon 2",
    "ema-beacon2": "EMA-Beacon 2",
    "ema beacon 2": "EMA-Beacon 2",
}

# Your original list (kept as fallback for non-model files)
DEVICE_NAME_OPTIONS_FALLBACK = [
    "XS-110G-A",
    "XS-010X-Q",
    "XS-010X-A",
    "Beacon G6",
    "Beacon 6",
    "EMA-XS-2426G-A",
    "EMA-Beacon 2",
    "EMA-XS-2426X-A",
    "EMA-XS-250X-AUSGeneric",
    "EMA-U-090CP-P",
    "EMA-XS-010S-Q",
    "CUST-OWNED-GATEWAY",
    "XS-2426X-A",
    "GS-HT802",
    "GS-HT814",
    "XS-230X-A",
    "Y-010Y-B",
    "GS-HT812",
    "GS-HT818",
    "XS-220X-A",
]

# -------------------------------------------------------------------
# Inventory location options (expanded list + CUSTOM)
# Keep "WAREHOUSE" because your existing behavior uses it.
# -------------------------------------------------------------------
INVENTORY_LOCATION_OPTIONS = [
    "WAREHOUSE",
    "AURRMO",
    "FIELD",
    "LBNNMO",
    "LOST",
    "MNTTMO",
    "MRFDMO",
    "MW-CBRANDON",
    "MW-DECHER",
    "MW-DECKER",
    "MW-DJONES",
    "MW-DOSS",
    "MW-ENGLEBRECHT",
    "MW-GRACIANO",
    "MW-HICKS",
    "MW-JONES",
    "MW-KELLNER",
    "MW-MEADOWS",
    "MW-PERIMAN",
    "MW-PITTS",
    "MW-RICHHART",
    "MW-SANDERSON",
    "MW-SBRANDON",
    "MW-YORK",
    "NESHMO",
    "NOT-RETURNED",
    "OZARK-FIBER",
    "PENDING CUST RETURN",
    "RECYCLEBIN",
    "TO-DELETE",
    "WH-SPFDMO",
    "WRITEOFF",
    "CUSTOM",
]

location_option = st.selectbox("Select Inventory Location", INVENTORY_LOCATION_OPTIONS)
custom_location = ""
if location_option == "CUSTOM":
    custom_location = st.text_input("Enter custom location code (e.g., WH-SPFDMO)").strip()

# ✅ Multiple files enabled here:
uploaded_files = st.file_uploader(
    "Choose one or more inventory CSV files",
    type=["csv"],
    accept_multiple_files=True,
)


def _normalize_company_for_filename(name: str) -> str:
    cleaned = re.sub(r"\s+", "_", name.strip())
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", cleaned)
    return cleaned or "company"


def _find_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    cols = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand in cols:
            return cols[cand]
    return None


def _looks_like_mac(s: str) -> bool:
    if not isinstance(s, str) or not s:
        return False
    s2 = s.replace(":", "").replace("-", "").lower()
    return len(s2) == 12 and all(ch in "0123456789abcdef" for ch in s2)


def _normalize_model_value(s: str) -> str:
    return str(s).strip().lower()


def _map_model_to_device_name(model_raw: str) -> str | None:
    # 1) exact canonical match
    if model_raw in DEVICE_PROFILE_BY_DEVICE_NAME:
        return model_raw
    # 2) alias match
    key = _normalize_model_value(model_raw)
    return MODEL_ALIASES_TO_DEVICE_NAME.get(key)


def _load_input_csv(file) -> pd.DataFrame:
    """Loads CSV robustly.

    If file has model column: returns columns model, mac, serial.
    If not: returns columns mac, serial (manual selection flow).
    Supports headerless 2-col mac/serial.
    """
    df = pd.read_csv(file, dtype=str).fillna("")
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    model_col = _find_col(df, ("model", "device_model", "device", "device_name", "equipment_model"))
    mac_col = _find_col(df, ("mac", "mac_address", "macaddress"))
    serial_col = _find_col(df, ("serial", "serial_number", "sn", "s/n", "serialno", "serial_no"))

    if model_col:
        if not mac_col or not serial_col:
            raise ValueError(
                "Model-based import detected, but missing required columns. "
                "Please include 'mac' and 'serial_number' (or 'serial'/'sn')."
            )
        return pd.DataFrame({
            "model": df[model_col].astype(str).str.strip(),
            "mac": df[mac_col].astype(str).str.strip(),
            "serial": df[serial_col].astype(str).str.strip(),
        })

    # --- Manual (non-model) behavior ---
    cols_lower = [str(c).strip().lower() for c in df.columns]
    has_mac = any(c in ("mac", "mac_address", "macaddress") for c in cols_lower)
    has_serial = any(c in ("serial", "serial_number", "sn", "s/n", "serialno", "serial_no") for c in cols_lower)

    if len(df.columns) == 2 and not (has_mac and has_serial):
        file.seek(0)
        df2 = pd.read_csv(file, header=None, names=["col1", "col2"], dtype=str).fillna("")
        df2 = df2.applymap(lambda x: x.strip() if isinstance(x, str) else x)

        mac_ratio_col1 = df2["col1"].map(_looks_like_mac).mean()
        mac_ratio_col2 = df2["col2"].map(_looks_like_mac).mean()

        if mac_ratio_col1 >= mac_ratio_col2:
            return pd.DataFrame({"mac": df2["col1"], "serial": df2["col2"]})
        return pd.DataFrame({"mac": df2["col2"], "serial": df2["col1"]})

    mac_col = _find_col(df, ("mac", "mac_address", "macaddress"))
    serial_col = _find_col(df, ("serial", "serial_number", "sn", "s/n", "serialno", "serial_no"))

    if not mac_col or not serial_col:
        raise ValueError(
            "Couldn't find required columns. Please include headers like 'mac' and 'serial' (or 'serial_number'/'sn'), "
            "or upload a 2-column headerless CSV."
        )

    return pd.DataFrame({
        "mac": df[mac_col].astype(str).str.strip(),
        "serial": df[serial_col].astype(str).str.strip(),
    })


def _build_device_numbers(device_profile: str, mac: str, serial: str) -> str:
    mac = (mac or "").strip()
    serial = (serial or "").strip()

    if device_profile in ("NOKIA_ONT", "NOKIA_MESH"):
        if not mac or not serial:
            raise ValueError("NOKIA devices require both MAC and Serial/SN.")
        if not _looks_like_mac(mac):
            raise ValueError(f"Invalid MAC format: {mac}")
        return f"MAC={mac}|SN={serial}"

    if device_profile == "VOIP_PHONE_ADAP":
        if not mac or not serial:
            raise ValueError("VOIP devices require both MAC and Serial/SN.")
        if not _looks_like_mac(mac):
            raise ValueError(f"Invalid MAC format: {mac}")
        return f"VOIP_MAC={mac}|VOIP_SN={serial}"

    if device_profile == "GEN_DEVICE":
        if not serial:
            raise ValueError("GEN_DEVICE requires Serial/SN.")
        return f"SN={serial}"

    # fallback
    if mac and serial:
        return f"MAC={mac}|SN={serial}"
    if serial:
        return f"SN={serial}"
    raise ValueError("Missing identifiers (need at least SN).")


# Manual fallback selectors (only used for files without model)
st.divider()
st.caption("Manual fallback (only used if a file does not include a 'model' column):")
manual_device_profile = st.selectbox("Device profile (manual fallback)", ["NOKIA_ONT", "NOKIA_MESH"])
manual_device_name = st.selectbox("Device name (manual fallback)", DEVICE_NAME_OPTIONS_FALLBACK)

# Proceed if everything required is present
location_is_set = (location_option != "CUSTOM") or bool(custom_location)

if uploaded_files and location_is_set:
    try:
        inventory_location = custom_location if location_option == "CUSTOM" else location_option

        all_final_frames = []
        summary_rows = []  # for quick summary

        unknown_models_accum = []
        file_errors = []

        for f in uploaded_files:
            try:
                df_in = _load_input_csv(f)
                df_in["source_file"] = getattr(f, "name", "uploaded.csv")

                if "model" in df_in.columns:
                    # Auto mapping flow
                    df_in["device_name"] = df_in["model"].map(_map_model_to_device_name)

                    missing = df_in[df_in["device_name"].isna()]
                    if len(missing) > 0:
                        unknown_models_accum.append(
                            missing[["source_file", "model", "mac", "serial"]].copy()
                        )
                        # skip building final rows for this file until mapping is fixed
                        continue

                    df_in["device_profile"] = df_in["device_name"].map(DEVICE_PROFILE_BY_DEVICE_NAME)

                    missing_prof = df_in[df_in["device_profile"].isna()]
                    if len(missing_prof) > 0:
                        # This means canonical device_name exists but no profile in dict
                        unknown_models_accum.append(
                            missing_prof[["source_file", "model", "device_name", "mac", "serial"]].copy()
                        )
                        continue

                    df_in["device_numbers"] = df_in.apply(
                        lambda r: _build_device_numbers(r["device_profile"], r["mac"], r["serial"]),
                        axis=1
                    )

                    final_df = pd.DataFrame({
                        "device_profile": df_in["device_profile"],
                        "device_name": df_in["device_name"],
                        "device_numbers": df_in["device_numbers"],
                        "inventory_location": inventory_location,
                        "inventory_status": "UNASSIGNED",
                    })

                    # Summary per file + model
                    model_counts = (
                        df_in.groupby(["source_file", "model", "device_name", "device_profile"])
                        .size()
                        .reset_index(name="count")
                    )
                    summary_rows.append(model_counts)

                else:
                    # Manual fallback flow for this file
                    final_df = pd.DataFrame({
                        "device_profile": manual_device_profile,
                        "device_name": manual_device_name,
                        "device_numbers": "MAC=" + df_in["mac"].astype(str) + "|SN=" + df_in["serial"].astype(str),
                        "inventory_location": inventory_location,
                        "inventory_status": "UNASSIGNED",
                    })

                    # Summary per file (manual)
                    summary_rows.append(pd.DataFrame([{
                        "source_file": df_in["source_file"].iloc[0],
                        "model": "(manual)",
                        "device_name": manual_device_name,
                        "device_profile": manual_device_profile,
                        "count": len(final_df),
                    }]))

                all_final_frames.append(final_df)

            except Exception as fe:
                file_errors.append((getattr(f, "name", "uploaded.csv"), str(fe)))

        # If any files had unknown models, show and stop so you can fix mapping
        if unknown_models_accum:
            st.error(
                "Some rows contain **model** values that are not mapped in the script.\n\n"
                "Fix by adding entries under **DEVICE_PROFILE_BY_DEVICE_NAME** and/or "
                "**MODEL_ALIASES_TO_DEVICE_NAME** (see instructions in the code)."
            )
            unknown_df = pd.concat(unknown_models_accum, ignore_index=True)
            st.dataframe(unknown_df.head(300))
            st.stop()

        if file_errors:
            st.warning("Some files could not be processed:")
            st.dataframe(pd.DataFrame(file_errors, columns=["file", "error"]))
            # continue if at least one file succeeded
            if not all_final_frames:
                st.stop()

        # Combine all output rows into one export
        combined_final = pd.concat(all_final_frames, ignore_index=True)

        # --- Quick Summary (models + counts + location) ---
        st.subheader("Quick Summary")
        st.write(f"**Chosen inventory_location:** `{inventory_location}`")
        st.write(f"**Total rows to export:** {len(combined_final)}")

        if summary_rows:
            summary_df = pd.concat(summary_rows, ignore_index=True)
            # Add location into summary for visibility (same for all rows)
            summary_df["inventory_location"] = inventory_location

            # Show per-file model counts
            st.caption("Per-file model counts (what was detected and how it mapped):")
            st.dataframe(
                summary_df.sort_values(["source_file", "count"], ascending=[True, False]),
                use_container_width=True
            )

            # Also show a rolled-up total
            rolled = (
                summary_df.groupby(["model", "device_name", "device_profile", "inventory_location"])["count"]
                .sum()
                .reset_index()
                .sort_values("count", ascending=False)
            )
            st.caption("Rolled-up totals across all uploaded files:")
            st.dataframe(rolled, use_container_width=True)

        # Show output preview
        st.subheader("Output Preview")
        st.dataframe(combined_final, use_container_width=True)

        # Output filename: company_date_.csv
        safe_company = _normalize_company_for_filename(company_name)
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_name = f"{safe_company}_{date_str}_.csv"

        csv_bytes = combined_final.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Combined Inventory CSV",
            data=csv_bytes,
            file_name=out_name,
            mime="text/csv",
        )

    except Exception as e:
        st.error(f"Error processing files: {e}")
else:
    st.info("Upload one or more CSV files and choose an inventory location to generate the output file.")
