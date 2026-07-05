FROM debian:bookworm-slim

ARG OPENTOFU_VERSION=1.10.6
ARG TFLINT_VERSION=0.58.1

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
    && unzip /tmp/tofu.zip -d /usr/local/bin tofu \
    && chmod 0755 /usr/local/bin/tofu \
    && rm -f /tmp/tofu.zip \
    && curl -fsSL -o /tmp/tflint.zip \
        "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_amd64.zip" \
    && unzip /tmp/tflint.zip -d /usr/local/bin tflint \
    && chmod 0755 /usr/local/bin/tflint \
    && rm -f /tmp/tflint.zip \
    && python3 -m venv /opt/ansible \
    && /opt/ansible/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/ansible/bin/pip install --no-cache-dir ansible-core ansible-lint jmespath requests \
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
