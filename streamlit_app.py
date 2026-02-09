import re
from datetime import datetime

import pandas as pd
import streamlit as st


# -----------------------------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Inventory CSV Builder", layout="centered")
st.title("Inventory CSV Builder")

st.markdown(
    "Upload one or more CSV files and export a combined inventory import file.\n\n"
    "- If a file includes a **model** column (recommended), the app will automatically set **device_name** and **device_profile**.\n"
    "- If a file does not include **model**, the app will use manual fallback selectors for that file.\n"
    "- You choose **inventory_location** once for all output rows.\n"
    "- Output **inventory_status** is always **UNASSIGNED**."
)

company_name = st.text_input(
    "Company name (used in output file name)",
    placeholder="e.g., AcmeFiber"
).strip()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _normalize_company_for_filename(name: str) -> str:
    cleaned = re.sub(r"\s+", "_", (name or "").strip())
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
    """
    Normalizes model strings so vendor suffixes / punctuation variations do not break mapping.

    Examples:
      "XS-220X-A (US plug)" -> "xs-220x-a"
      " XS 220X A "         -> "xs-220x-a"
      "ema-xs-2426x-a"      -> "ema-xs-2426x-a"
    """
    s = str(s or "").strip().lower()

    # Remove any parenthetical suffix, e.g. "(US plug)", "(rev 2)"
    s = re.sub(r"\(.*?\)", "", s)

    # Normalize separators/spaces
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)

    # Collapse multiple hyphens
    s = re.sub(r"-{2,}", "-", s).strip("-")

    return s


def _extract_canonical_model_token(model_raw: str) -> str | None:
    """
    Extract a Nokia-style model token from a free-form model string.

    Matches examples like:
      XS-220X-A
      EMA-XS-2426X-A
      XS-220X-A-US (will extract XS-220X-A)
    """
    upper = str(model_raw or "").upper()

    # Prefer longer matches that include EMA- prefix when present.
    m = re.search(r"(EMA-)?XS-[0-9A-Z]+(?:[0-9A-Z-]*?)-[A-Z]", upper)
    if not m:
        return None

    token = m.group(0)

    # If the match includes extra suffix segments, trim back to the canonical pattern
    # that ends with "-<letter>".
    m2 = re.search(r"(EMA-)?XS-[0-9A-Z]+(?:[0-9A-Z]*?)-[A-Z]$", token)
    if m2:
        return m2.group(0)

    return token


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

    # Fallback
    if mac and serial:
        return f"MAC={mac}|SN={serial}"
    if serial:
        return f"SN={serial}"
    raise ValueError("Missing identifiers (need at least SN).")


def _load_input_csv(file) -> pd.DataFrame:
    """
    Load an input CSV.

    If a model column exists, returns: model, mac, serial
    Otherwise returns: mac, serial

    Supports 2-column headerless CSVs (auto-detect which column is MAC).
    """
    df = pd.read_csv(file, dtype=str).fillna("")
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    model_col = _find_col(df, ("model", "device_model", "equipment_model", "device"))
    mac_col = _find_col(df, ("mac", "mac_address", "macaddress"))
    serial_col = _find_col(df, ("serial", "serial_number", "sn", "s/n", "serialno", "serial_no"))

    if model_col:
        if not mac_col or not serial_col:
            raise ValueError(
                "Model-based import detected, but missing required columns. "
                "Include 'mac' and 'serial_number' (or 'serial'/'sn')."
            )
        return pd.DataFrame({
            "model": df[model_col].astype(str).str.strip(),
            "mac": df[mac_col].astype(str).str.strip(),
            "serial": df[serial_col].astype(str).str.strip(),
        })

    # Manual (non-model) behavior
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
            "Could not find required columns. Include headers like 'mac' and 'serial' "
            "(or 'serial_number'/'sn'), or upload a 2-column headerless CSV."
        )

    return pd.DataFrame({
        "mac": df[mac_col].astype(str).str.strip(),
        "serial": df[serial_col].astype(str).str.strip(),
    })


# -----------------------------------------------------------------------------
# Device mapping (authoritative)
# -----------------------------------------------------------------------------
# Canonical device_name -> device_profile mapping.
DEVICE_PROFILE_BY_DEVICE_NAME = {
    # Nokia Mesh
    "Beacon G6": "NOKIA_MESH",
    "Beacon 6": "NOKIA_MESH",
    "EMA-Beacon 2": "NOKIA_MESH",

    # Nokia ONT
    "XS-110G-A": "NOKIA_ONT",
    "XS-230X-A": "NOKIA_ONT",
    "XS-220X-A": "NOKIA_ONT",
    "XS-2426X-A": "NOKIA_ONT",
    "EMA-XS-2426X-A": "NOKIA_ONT",
    "EMA-XS-2426G-A": "NOKIA_ONT",
    "EMA-XS-010S-Q": "NOKIA_ONT",
    "EMA-XS-250X-AUSGeneric": "NOKIA_ONT",
    "XS-010X-Q": "NOKIA_ONT",
    "XS-010X-A": "NOKIA_ONT",
    "Y-010Y-B": "NOKIA_ONT",

    # VoIP / ATA
    "GS-HT802": "VOIP_PHONE_ADAP",
    "GS-HT812": "VOIP_PHONE_ADAP",
    "GS-HT814": "VOIP_PHONE_ADAP",
    "GS-HT818": "VOIP_PHONE_ADAP",

    # General
    "CUST-OWNED-GATEWAY": "GEN_DEVICE",
    "EMA-U-090CP-P": "GEN_DEVICE",
}

# Model aliases (normalized) -> canonical device_name.
# Keys are expected to be normalized by _normalize_model_value().
MODEL_ALIASES_TO_DEVICE_NAME = {
    # Beacon G6 variations
    "beacong6": "Beacon G6",
    "beacon-g6": "Beacon G6",
    "beacon-g6-wifi6": "Beacon G6",
    "beacon-g6-wifi-6": "Beacon G6",
    "beacon-g6-wifi-6e": "Beacon G6",

    # Beacon 6 variations
    "beacon6": "Beacon 6",
    "beacon-6": "Beacon 6",

    # EMA-Beacon 2 variations
    "emabeacon2": "EMA-Beacon 2",
    "ema-beacon2": "EMA-Beacon 2",
    "ema-beacon-2": "EMA-Beacon 2",
}


def _map_model_to_device_name(model_raw: str) -> str | None:
    # 1) Exact canonical match
    if model_raw in DEVICE_PROFILE_BY_DEVICE_NAME:
        return model_raw

    # 2) Extract a canonical token from free-form model strings
    token = _extract_canonical_model_token(model_raw)
    if token and token in DEVICE_PROFILE_BY_DEVICE_NAME:
        return token

    # 3) Normalized alias match (handles suffixes like "(US plug)")
    key = _normalize_model_value(model_raw)
    return MODEL_ALIASES_TO_DEVICE_NAME.get(key)


# Fallback device_name list for manual flow
DEVICE_NAME_OPTIONS_FALLBACK = sorted(DEVICE_PROFILE_BY_DEVICE_NAME.keys())


# -----------------------------------------------------------------------------
# Inventory location
# -----------------------------------------------------------------------------
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

location_option = st.selectbox("Inventory location", INVENTORY_LOCATION_OPTIONS)
custom_location = ""
if location_option == "CUSTOM":
    custom_location = st.text_input("Custom location code (e.g., WH-SPFDMO)").strip()

uploaded_files = st.file_uploader(
    "Choose one or more inventory CSV files",
    type=["csv"],
    accept_multiple_files=True,
)

st.divider()
st.caption("Manual fallback (used only if a file does not include a 'model' column):")
manual_device_profile = st.selectbox("Device profile (manual fallback)", ["NOKIA_ONT", "NOKIA_MESH", "VOIP_PHONE_ADAP", "GEN_DEVICE"])
manual_device_name = st.selectbox("Device name (manual fallback)", DEVICE_NAME_OPTIONS_FALLBACK)

location_is_set = (location_option != "CUSTOM") or bool(custom_location)


# -----------------------------------------------------------------------------
# Processing
# -----------------------------------------------------------------------------
if uploaded_files and location_is_set:
    try:
        inventory_location = custom_location if location_option == "CUSTOM" else location_option

        all_final_frames: list[pd.DataFrame] = []
        summary_rows: list[pd.DataFrame] = []
        unknown_models_accum: list[pd.DataFrame] = []
        file_errors: list[tuple[str, str]] = []

        for f in uploaded_files:
            filename = getattr(f, "name", "uploaded.csv")
            try:
                df_in = _load_input_csv(f)
                df_in["source_file"] = filename

                if "model" in df_in.columns:
                    df_in["device_name"] = df_in["model"].map(_map_model_to_device_name)

                    missing_name = df_in[df_in["device_name"].isna()].copy()
                    if not missing_name.empty:
                        missing_name["normalized_model"] = missing_name["model"].map(_normalize_model_value)
                        missing_name["suggested_device_name"] = missing_name["model"].map(_extract_canonical_model_token)
                        unknown_models_accum.append(
                            missing_name[["source_file", "model", "normalized_model", "suggested_device_name", "mac", "serial"]]
                        )
                        continue

                    df_in["device_profile"] = df_in["device_name"].map(DEVICE_PROFILE_BY_DEVICE_NAME)

                    missing_prof = df_in[df_in["device_profile"].isna()].copy()
                    if not missing_prof.empty:
                        missing_prof["normalized_model"] = missing_prof["model"].map(_normalize_model_value)
                        missing_prof["suggested_device_name"] = missing_prof["model"].map(_extract_canonical_model_token)
                        unknown_models_accum.append(
                            missing_prof[["source_file", "model", "device_name", "normalized_model", "suggested_device_name", "mac", "serial"]]
                        )
                        continue

                    # Build device_numbers with validation by profile
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

                    model_counts = (
                        df_in.groupby(["source_file", "model", "device_name", "device_profile"])
                        .size()
                        .reset_index(name="count")
                    )
                    summary_rows.append(model_counts)

                else:
                    # Manual fallback flow
                    df_in["device_profile"] = manual_device_profile
                    df_in["device_name"] = manual_device_name
                    df_in["device_numbers"] = df_in.apply(
                        lambda r: _build_device_numbers(manual_device_profile, r["mac"], r["serial"]),
                        axis=1
                    )

                    final_df = pd.DataFrame({
                        "device_profile": df_in["device_profile"],
                        "device_name": df_in["device_name"],
                        "device_numbers": df_in["device_numbers"],
                        "inventory_location": inventory_location,
                        "inventory_status": "UNASSIGNED",
                    })

                    summary_rows.append(pd.DataFrame([{
                        "source_file": filename,
                        "model": "(manual)",
                        "device_name": manual_device_name,
                        "device_profile": manual_device_profile,
                        "count": len(final_df),
                    }]))

                all_final_frames.append(final_df)

            except Exception as fe:
                file_errors.append((filename, str(fe)))

        if unknown_models_accum:
            st.error(
                "One or more files contain model values that do not map to a known device_name/device_profile. "
                "Update DEVICE_PROFILE_BY_DEVICE_NAME and/or MODEL_ALIASES_TO_DEVICE_NAME in this script."
            )
            unknown_df = pd.concat(unknown_models_accum, ignore_index=True)
            st.dataframe(unknown_df.head(500), use_container_width=True)
            st.stop()

        if file_errors:
            st.warning("Some files could not be processed.")
            st.dataframe(pd.DataFrame(file_errors, columns=["file", "error"]), use_container_width=True)
            if not all_final_frames:
                st.stop()

        combined_final = pd.concat(all_final_frames, ignore_index=True)

        st.subheader("Quick Summary")
        st.write(f"Chosen inventory_location: `{inventory_location}`")
        st.write(f"Total rows to export: {len(combined_final)}")

        if summary_rows:
            summary_df = pd.concat(summary_rows, ignore_index=True)
            summary_df["inventory_location"] = inventory_location

            st.caption("Per-file model counts (detected model -> mapped device):")
            st.dataframe(
                summary_df.sort_values(["source_file", "count"], ascending=[True, False]),
                use_container_width=True
            )

            rolled = (
                summary_df.groupby(["model", "device_name", "device_profile", "inventory_location"])["count"]
                .sum()
                .reset_index()
                .sort_values("count", ascending=False)
            )

            st.caption("Rolled-up totals:")
            st.dataframe(rolled, use_container_width=True)

        st.subheader("Output Preview")
        st.dataframe(combined_final.head(300), use_container_width=True)

        out_company = _normalize_company_for_filename(company_name)
        out_date = datetime.now().strftime("%Y%m%d")
        out_filename = f"{out_date}-{out_company}-inventory-import.csv"

        csv_bytes = combined_final.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download Inventory Import CSV",
            data=csv_bytes,
            file_name=out_filename,
            mime="text/csv",
        )

    except Exception as e:
        st.error(str(e))
elif uploaded_files and not location_is_set:
    st.warning("Select an inventory location (or enter a custom location) to continue.")
