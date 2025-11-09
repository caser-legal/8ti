#!/bin/bash
cd /home/sm/caser-search
export TYPESENSE_ADMIN_KEY='-RH%PL0H}h<<j:_eLc0k)!5r`Mbr)xD._cm(v!55j^bkg9'
source .venv/bin/activate
python src/rss_scanner.py
