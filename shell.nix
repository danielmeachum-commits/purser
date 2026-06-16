{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  packages = with pkgs; [
    uv
  ];

  # Expose libstdc++ (and friends) to the dynamic loader so Python wheels
  # with native deps — grpc's cython extension, etc. — load cleanly.
  # Prefers nix-ld's lib set when available so we inherit whatever the
  # system config has declared; falls back to stdenv.cc.cc.lib otherwise.
  shellHook = ''
    if [ -n "$NIX_LD_LIBRARY_PATH" ]; then
      export LD_LIBRARY_PATH="$NIX_LD_LIBRARY_PATH''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    else
      export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
  '';
}
