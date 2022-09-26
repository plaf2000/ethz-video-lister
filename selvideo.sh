#!/bin/bash

orig_path=`dirname .`
path=`dirname $0`
cd "${path}"
select video in videolinks_*.txt
do
	mpv --playlist="$path/$video"
done

cd orig_path
