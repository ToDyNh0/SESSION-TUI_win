# syntax=docker/dockerfile:1
#
# Session TUI - Windows build in Docker (from any OS, no Python or Windows needed)
#
# Cross-builds dist\session-tui.exe with Windows Python running under Wine,
# after running the offline test suite with that same Python:
#
#     docker build --output dist .
#
# The result is the same file build.bat produces on Windows.

FROM tobix/pywine:3.12 AS build
WORKDIR /src

# dependencies first: this layer is cached while only the code changes
COPY requirements.txt requirements-build.txt ./
RUN wine python -m pip install --no-cache-dir --disable-pip-version-check \
        -r requirements.txt -r requirements-build.txt

COPY . .
RUN wine python selftest.py \
 && wine python build_exe.py

# only the .exe leaves the build (docker build --output dist .)
FROM scratch AS export
COPY --from=build /src/dist/session-tui.exe /
