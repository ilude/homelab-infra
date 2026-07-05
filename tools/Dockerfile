FROM debian:bookworm-slim

ARG OPENTOFU_VERSION=1.12.3
ARG OPENTOFU_LINUX_AMD64_SHA256=46b48c3438c65cf479fc076c9281422ffa2f493548d1e813d154c835c5986a08
ARG TFLINT_VERSION=0.63.1
ARG TFLINT_LINUX_AMD64_SHA256=8441a7d97df20431f19c9b9d27ff4c63e308c964e86660bc7cc0cf7bbe0725e8
ARG PIP_VERSION=26.1.2

COPY tools/requirements.txt /tmp/requirements.txt

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/ansible/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    TF_PLUGIN_CACHE_DIR=/root/.terraform.d/plugin-cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        gosu \
        jq \
        openssh-client \
        python3 \
        python3-pip \
        python3-venv \
        shellcheck \
        unzip \
    && curl -fsSL -o /tmp/tofu.zip \
        "https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_linux_amd64.zip" \
    && printf '%s  %s\n' "${OPENTOFU_LINUX_AMD64_SHA256}" /tmp/tofu.zip | sha256sum -c - \
    && unzip /tmp/tofu.zip -d /usr/local/bin tofu \
    && chmod 0755 /usr/local/bin/tofu \
    && rm -f /tmp/tofu.zip \
    && curl -fsSL -o /tmp/tflint.zip \
        "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_amd64.zip" \
    && printf '%s  %s\n' "${TFLINT_LINUX_AMD64_SHA256}" /tmp/tflint.zip | sha256sum -c - \
    && unzip /tmp/tflint.zip -d /usr/local/bin tflint \
    && chmod 0755 /usr/local/bin/tflint \
    && rm -f /tmp/tflint.zip \
    && python3 -m venv /opt/ansible \
    && /opt/ansible/bin/pip install --no-cache-dir --upgrade "pip==${PIP_VERSION}" \
    && /opt/ansible/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --shell /bin/bash --uid 1000 anvil \
    && mkdir -p /home/anvil/.terraform.d/plugin-cache /home/anvil/.ansible /workspace \
    && chown -R anvil:anvil /home/anvil /workspace \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY tools/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

ENV HOME=/home/anvil \
    TF_PLUGIN_CACHE_DIR=/home/anvil/.terraform.d/plugin-cache
WORKDIR /workspace

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["bash"]
