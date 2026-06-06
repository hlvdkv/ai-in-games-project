{ pkgs ? import <nixpkgs> {} }:
let 
  lib-path = with pkgs; lib.makeLibraryPath [
    libffi
    openssl
    stdenv.cc.cc
  ];
in 
pkgs.mkShell {
  packages = with pkgs; [
    python3
    python3Packages.venvShellHook
    
    # add any packages you can from nixpkgs
    # add the rest in requirements.txt
    pandoc
    texliveSmall
  ];

  shellHook = ''
    SOURCE_DATE_EPOCH=$(date +%s)
    export "LD_LIBRARY_PATH=$LD_LIBRARY_PATH:${lib-path}"
    VENV=.venv

    if test ! -d $VENV; then
      python -m venv $VENV
    fi
    source ./$VENV/bin/activate
    export PYTHONPATH=`pwd`/$VENV/${pkgs.python3.sitePackages}/:$PYTHONPATH
  '';

  postShellHook = ''
    ln -sf ${pkgs.python3.sitePackages}/* ./.venv/lib/python3.13/site-packages
  '';
}
