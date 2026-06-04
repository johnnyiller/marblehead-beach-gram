.PHONY: install sample generate list-backgrounds backgrounds post-dry clean

install:
	pip install -r requirements.txt

sample:
	python scripts/generate.py --sample

generate:
	python scripts/generate.py

list-backgrounds:
	python scripts/generate.py --list-art-directions

backgrounds:
	python scripts/generate.py --sample --background-variants 6

post-dry:
	DRY_RUN=true python scripts/post_instagram.py

clean:
	rm -f site/latest.png site/latest.jpg site/latest.json
	rm -f site/assets/tidegram-*.png site/assets/tidegram-*.jpg
