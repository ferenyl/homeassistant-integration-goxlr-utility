# Home Assistant Integration - GoXLR Utility

Originally a fork of https://github.com/timmo001/homeassistant-integration-goxlr-utility wich is now archived.

[GoXLR Utility](https://github.com/GoXLR-on-Linux/goxlr-utility) integration for [Home Assistant](https://www.home-assistant.io/) using the https://github.com/ferenyl/goxlrutil_api Python package. This is a third party application from [@GoXLR-on-Linux](https://github.com/GoXLR-on-Linux) that allows for control of the GoXLR on Linux, Mac and Windows.

> This integration does not connect to the official GoXLR application!

Be sure to check out the [GoXLR Utility](https://github.com/GoXLR-on-Linux/goxlr-utility) project for more information.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ferenyl&repository=homeassistant-integration-goxlr-utility&category=integration)

This integration is available in the [Home Assistant Community Store](https://hacs.xyz/).

## Setup and Configuration

- Enable `Allow UI network access` the the settings to allow remote access on the network
- Add to Home Assistant using the UI

## Features

### Controls

- Volume sliders and mute control for GoXLR audio channels.
- Profile selection for both the main profile and microphone profile.
- Routing matrix switches for input-to-output routes.
- Lighting control for Accent, button colors, and fader colors.

### Sensors

- Current profile.
- Current microphone profile.

### Diagnostics

- Button press state sensors for automations and troubleshooting.
