#!/bin/sh

export USERNAME=${USERNAME:=mbryan}
export PASSWORD=${PASSWORD:=Phone99Board}
export GATEWAY=${GATEWAY:=remote.wintechengineering.com.au}
export COMPUTER=${COMPUTER:=OFFICE26}

export OPTIONS="/dynamic-resolution /drive:michael,$HOME -aero"

# Make sure a ctrl-c kills this script
#trap exit SIGINT

log() {
	RANDOM_COLOUR=$(( $RANDOM % $(tput colors) ))
	tput bold && tput smul && tput setaf $RANDOM_COLOUR
	echo -e $@
	tput sgr0
}

log "\tLogging into $USERNAME@$COMPUTER via $GATEWAY"
echo
exec xfreerdp $OPTIONS /u:$USERNAME /p:$PASSWORD /g:$GATEWAY /v:$COMPUTER "$@"
