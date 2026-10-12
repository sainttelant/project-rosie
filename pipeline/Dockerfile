FROM griffithlab/pvactools:latest

# MHCflurry is a Python package (installed via requirements.txt below).
# MixMHCpred 3.0 is a bash+Python tool installed from its GitHub repo (v3.0 tag).
# Both are installed at build time — no external binary download is required.

# Install MixMHCpred 3.0 (pan-allele MHC-I predictor, supports non-human alleles)
# Use a zip download instead of git clone to avoid intermittent network failures.
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip mafft \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /opt/MixMHCpred \
    && curl -L https://github.com/GfellerLab/MixMHCpred/archive/refs/tags/v3.0.zip -o /tmp/mixmhcpred.zip \
    && unzip -q /tmp/mixmhcpred.zip -d /opt \
    && mv /opt/MixMHCpred-3.0 /opt/MixMHCpred \
    && chmod +x /opt/MixMHCpred/MixMHCpred \
    && ln -sf /opt/MixMHCpred/MixMHCpred /usr/local/bin/MixMHCpred \
    && rm -f /tmp/mixmhcpred.zip

# NetMHCpan installation removed; using mhcnuggets (Python package) for DLA alleles.

ENV TMPDIR=/tmp
ENV PATH="$PATH:/opt/MixMHCpred"

# Force TensorFlow (used by MHCflurry) to run in CPU-only mode.
# Without this, TF tries to load CUDA libraries and crashes with
# "Error loading CUDA libraries" when the container has no GPU drivers.
# The GPU is only needed for AlphaFold2 (separate container), not for MHCflurry.
ENV TF_ENABLE_ONEDNN_OPTS=0
ENV CUDA_VISIBLE_DEVICES=""

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Patch mhcflurry for TensorFlow 2.x compatibility.
# mhcflurry's configure_tensorflow() calls
#   tensorflow.compat.v1.keras.backend.set_session(session)
# which was removed in newer TensorFlow releases, causing:
#   AttributeError: module 'keras._tf_keras.keras.backend' has no attribute 'set_session'
# In TF2 compat mode set_session only sets the default v1 session and is safe to skip,
# so we wrap it in a try/except to keep MHCflurry working.
RUN python - <<'PY'
import re, pathlib
p = pathlib.Path("/usr/local/lib/python3.11/site-packages/mhcflurry/common.py")
src = p.read_text()
old = "    tensorflow.compat.v1.keras.backend.set_session(session)"
new = (
    "    try:\n"
    "        tensorflow.compat.v1.keras.backend.set_session(session)\n"
    "    except AttributeError:\n"
    "        pass  # set_session removed in newer TF; safe to skip in TF2 compat mode"
)
if old in src and new not in src:
    p.write_text(src.replace(old, new))
    print("Patched mhcflurry common.py set_session")
else:
    print("mhcflurry patch not needed or already applied")
PY

COPY modules/ ./modules/
COPY run_pipeline.py .
COPY run_cloud.py .

ENV VEP_CACHE_DIR=/vep_cache
ENV PYTHONUNBUFFERED=1
# The original image was built for Cloud Run Jobs and used run_cloud.py as the entrypoint.
# For local development we want the container to execute the CLI pipeline directly.
# Switching the entrypoint to run_pipeline.py allows users to pass all command‑line arguments
# (e.g. VCF path, predictors, structure flags) without needing to override it at `docker run`.
ENTRYPOINT ["python", "run_pipeline.py"]
