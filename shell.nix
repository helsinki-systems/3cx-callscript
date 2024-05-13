with import <nixpkgs> { };
let
  py = python3.withPackages (
    ps: with ps; [
      websocket_client
      requests
    ]
  );
in
pkgs.mkShell { buildInputs = [ py ]; }
