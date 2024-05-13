# Helsinki Callscript

This python script can be used to trigger calls on a desk phone connected to a 3cx pbx.

To use, install the dependencies by using poetry or your favorite way of installing python packages.
You'll need "some recent" versions of `websocket-client` and `requests`.

Then, call the script by running `PBX_URL=my3cxinstallation.my3cx.de python ./main.py $EXTENSION $PASSWORD $NUMBER_TO_CALL`.

You can also move the script somewhere and place it in your `$PATH` to run it like `helsinki-call-cli ...`.
