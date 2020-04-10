#!/bin/sh

laptop=eDP-1
trackpad=HDMI-1
external_hdmi=HDMI-2

current_state() {
  local output=$1
  xrandr | grep $output | awk '{ print $2 }'
}

case $(current_state $external_hdmi) in
	connected)
		xrandr --output $laptop --primary --mode 1920x1080 --pos 0x1080 --rotate normal \
		       --output $trackpad --off \
		       --output $external_hdmi --mode 1920x1080 --pos 0x0 --rotate normal
		i3-msg --quiet '[workspace=1] move workspace to HDMI-2'
		i3-msg --quiet '[workspace=2] move workspace to output eDP-1'
	;;

	disconnected)
		xrandr --output $laptop --primary --mode 1920x1080 --pos 0x1080 --rotate normal \
		       --output $trackpad --off \
		       --output $external_hdmi --off
	;;

	*)
		echo "Unable to determine if $external_hdmi is connected or disconnected"
		exit 1
	;;
esac

