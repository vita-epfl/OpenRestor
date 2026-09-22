FROM python:3.11-slim

# Cluster identity. On EPFL RCP these must match the submitting user so that
# files written to the mounted scratch PVC are owned by that user rather than root.
ARG LDAP_GROUPNAME=openrestore
ARG LDAP_GID=1000
ARG LDAP_USERNAME=openrestore
ARG LDAP_UID=1000

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY openrestore ./openrestore
COPY configs ./configs
COPY schemas ./schemas
# pyroomacoustics has no wheel for this interpreter, so it is compiled here and
# the toolchain is removed again to keep the runtime image small.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && python -m pip install --no-cache-dir . \
 && apt-get purge -y --auto-remove build-essential && rm -rf /var/lib/apt/lists/*

# Create the group and user only when the IDs are not already taken by the base image.
RUN if ! getent group "${LDAP_GID}" >/dev/null; then groupadd -g "${LDAP_GID}" "${LDAP_GROUPNAME}"; fi \
 && if ! getent passwd "${LDAP_UID}" >/dev/null; then useradd -m -u "${LDAP_UID}" -g "${LDAP_GID}" -s /bin/bash "${LDAP_USERNAME}"; fi
USER ${LDAP_UID}:${LDAP_GID}

# The image ships the code, but the package is also importable from a mounted
# checkout: `cd /path/to/repo && python -m openrestore.data.cli ...`.
ENTRYPOINT ["python", "-m"]
