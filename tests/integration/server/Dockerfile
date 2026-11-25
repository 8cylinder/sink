ARG UBUNTU_VERSION=26.04
FROM ubuntu:${UBUNTU_VERSION}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        default-mysql-client \
        openssh-server \
        rsync \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# sshd rejects locked accounts even for key authentication.  Give the
# account a password hash so it is not locked; sshd_config still disables
# password authentication, so only the injected key can log in.
RUN useradd --create-home --shell /bin/bash deploy \
    && echo 'deploy:sink-test-disabled-password' | chpasswd \
    && mkdir -p /run/sshd /home/deploy/.ssh /var/www \
    && touch /home/deploy/.ssh/authorized_keys \
    && chown -R deploy:deploy /home/deploy/.ssh \
    && chmod 700 /home/deploy/.ssh \
    && chmod 600 /home/deploy/.ssh/authorized_keys \
    && echo 'deploy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/deploy \
    && chmod 0440 /etc/sudoers.d/deploy

COPY sshd_config /etc/ssh/sshd_config
COPY entrypoint.sh /usr/local/bin/sink-test-entrypoint
RUN chmod 0755 /usr/local/bin/sink-test-entrypoint

EXPOSE 22
ENTRYPOINT ["/usr/local/bin/sink-test-entrypoint"]
