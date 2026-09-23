FROM gradle:8.7-jdk17 AS build

USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates && rm -rf /var/lib/apt/lists/*

ENV ANDROID_SDK_ROOT=/opt/android-sdk
RUN mkdir -p $ANDROID_SDK_ROOT/cmdline-tools && \
    curl -fsSL -o /tmp/cmdline-tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip && \
    unzip -q /tmp/cmdline-tools.zip -d /tmp/cmdline-tools && \
    mv /tmp/cmdline-tools/cmdline-tools $ANDROID_SDK_ROOT/cmdline-tools/latest && \
    yes | $ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null || true && \
    $ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager "platforms;android-35" "build-tools;35.0.0"

WORKDIR /workspace
COPY . .
RUN gradle --no-daemon assembleDebug && cp app/build/outputs/apk/debug/app-debug.apk /tmp/Windsor.apk

FROM python:3.12-slim
WORKDIR /srv
COPY --from=build /tmp/Windsor.apk /srv/Windsor.apk
EXPOSE 8080
CMD ["python","-m","http.server","8080","--directory","/srv"]
