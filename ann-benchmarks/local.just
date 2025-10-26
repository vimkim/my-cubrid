run-xs-n2-local:
    python run.py --dataset random-xs-20-angular --algorithm n2 --local --force --parallism 8

run-xs-cubrid_faiss-local:
    python run.py --dataset random-xs-20-angular --algorithm cubrid --local --force --parallism 8

create-website:
    mkdir websites/temp
    python create_website.py --outputdir websites/temp --scatter

serve-website:
    miniserve -p 8000 websites
