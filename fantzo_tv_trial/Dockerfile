FROM ghcr.io/cirruslabs/android-sdk:35

USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip python3 ca-certificates && rm -rf /var/lib/apt/lists/*

ARG GRADLE_VERSION=8.9
RUN curl -fsSL "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" -o /tmp/gradle.zip \
    && mkdir -p /opt/gradle \
    && unzip -q /tmp/gradle.zip -d /opt/gradle \
    && rm /tmp/gradle.zip

ENV PATH="/opt/gradle/gradle-${GRADLE_VERSION}/bin:${PATH}"
WORKDIR /workspace
COPY . .

CMD ["bash", "-lc", "gradle --no-daemon :app:assembleDebug && mkdir -p /out && cp app/build/outputs/apk/debug/app-debug.apk /out/fantzo-tv-trial.apk && python3 serve_apk.py"]
