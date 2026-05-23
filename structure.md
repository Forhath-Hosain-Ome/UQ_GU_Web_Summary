1. Before Uploading the Buyer and factory needs to be registered in the database. 
2. In the database the Buyer-Factory Pair will have a field as report type(Knit-35, Woven-37, Woven-78, Sweater-37 Etc) and available reports(Final, Re-final, In-Line, Sample etc choosen from a dropdown)
3. When uploading the excels the user will select the factory, buyer and date(unspection date.) So, date won't be extracted from excel.
4. The extraction label, type resolver, proximity, validation etc will be validated in single files for a input. Like For REPORT_NO a .py will be there, ITEM_NAME for item name one will be there. Like this so managing one field is easy. and everything will be inported in __init__.py so There isn't import mess.
5. Extraction logic for every report type will be different. as the report structure is different. There are some same fields that'll be common used in all formet.
5. For if error happens then for the retry there will be search option (by date and style 2 field) and a button to search or default view the last 20 entry as a list and download json option. And to upload the fixed json before the search section give a upload file field and a (upload fixed json) button.
6. for export it's ok.
7. Other's are ok. 