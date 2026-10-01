# The wake-word toolbox (ADR-329): synthesise, augment, train, measure — offline.
#
# It never runs on the API's interpreter nor on the Raspberry Pi: its only output
# is a handful of ONNX files and their manifest, committed under
# apps/web/public/models/wake/ and served to the browser as static assets.
#
#   task wake:image                 # build this image
#   task wake:train -- fr           # synthesise, train and measure one language
#
# Large inputs (corpora, voices, features) live in the named volume
# `lia-wake-data`, never in the repository.
FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /toolbox

COPY requirements.lock.txt requirements.reference.txt ./
# openWakeWord is the REFERENCE the features and the streaming detector are
# checked against (`python -m wakeword selfcheck`): installed without its
# dependencies, whose tflite-runtime has no wheel for this interpreter and is
# never used here (inference_framework="onnx").
RUN pip install --require-hashes \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.lock.txt \
    && pip install --no-deps --require-hashes -r requirements.reference.txt

COPY wakeword ./wakeword

ENTRYPOINT ["python", "-m", "wakeword"]
