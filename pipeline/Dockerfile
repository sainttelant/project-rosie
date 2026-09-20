FROM griffithlab/pvactools:latest

# MHCflurry is a Python package (installed via requirements.txt below).
# MixMHCpred 3.0 is a bash+Python tool installed from its GitHub repo (v3.0 tag).
# Both are installed at build time — no external binary download is required.

# Install MixMHCpred 3.0 (pan-allele MHC-I predictor, supports non-human alleles)
RUN apt-get update && apt-get install -y --no-install-recommends git mafft \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 --branch v3.0 https://github.com/GfellerLab/MixMHCpred.git /opt/MixMHCpred \
    && chmod +x /opt/MixMHCpred/MixMHCpred \
    && ln -s /opt/MixMHCpred/MixMHCpred /usr/local/bin/MixMHCpred

ENV TMPDIR=/tmp
ENV PATH="$PATH:/opt/MixMHCpred"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/ ./modules/
COPY run_pipeline.py .
COPY run_cloud.py .

ENV VEP_CACHE_DIR=/vep_cache
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "run_cloud.py"]
