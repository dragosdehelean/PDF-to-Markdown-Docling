Aceasta aplicatie CLI trebuie sa converteasca in modul cel mai profesionist un raport financiar in format pdf intr-un fisier .md, care sa fie apoi pasat unui RAG specializat in rapoarte financiare.

Analizeaza problemele aparute in conversia de la "long_report.pdf" la "long_report.md" si propune solutii incrementale de rezolvarea ale acestor probleme, care insa sa fie generice, deci aplicabile pentru orice alt raport financiar .pdf. 

Daca este nevoie sa faci diverse teste de calitate, nu aglomera totul in main.py.

Foloseste atunci cand este un best practice principiul decoupling-ului. Decupleaza logica principala de procesare din main.py, in alte fisiere de utilitati, de configurari sau de algoritimi de post-procesare. 

Aplica solutii de post-procesare doar in ultima instanta, dupa ce ai epuizat tot ce-ti poate oferi Docling.

Cerceteaza mereu documentatia si bunele practici de la https://www.docling.ai/ sau din alte surse autoritare si actuale despre procesarea rapoartelor financiare pentru AI/LLM.