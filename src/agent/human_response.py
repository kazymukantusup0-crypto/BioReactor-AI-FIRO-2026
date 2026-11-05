"""Plain-language, grounded presentation of the same structured calculations."""
def friendly(paragraphs,language):
    meanings={
      'ru':{'LITERATURE_ESTIMATE':'оценка по публикациям','HYPOTHETICAL_SCENARIO':'условный пример','MEASURED':'по измеренным характеристикам',
            'CONDITIONALLY_PROCESSING_PREFERRED':'переработка может быть выгоднее при названных условиях','CONDITIONALLY_SELLING_PREFERRED':'продажа может быть выгоднее при названных условиях','PROCESSING_PREFERRED':'переработка предпочтительнее в заданном сравнении','SELLING_PREFERRED':'продажа предпочтительнее в заданном сравнении','INSUFFICIENT_EVIDENCE':'победитель пока не установлен',
            'B_heat':'использования для отопления','C_electricity':'собственного электричества','CHP':'совместной выработки тепла и электричества','по BMP':'по лабораторному испытанию',' VS':' органического вещества','КПД':'КПД (эффективность преобразования энергии)'},
      'en':{'LITERATURE_ESTIMATE':'estimate from published studies','HYPOTHETICAL_SCENARIO':'conditional example','MEASURED':'based on measured properties','B_heat':'own heating','C_electricity':'own electricity','INSUFFICIENT_EVIDENCE':'no supported winner'},
      'kk':{'LITERATURE_ESTIMATE':'жарияланған зерттеулер бойынша бағалау','HYPOTHETICAL_SCENARIO':'шартты мысал','MEASURED':'өлшенген қасиеттер бойынша','B_heat':'жылыту','C_electricity':'өз электр энергиясы','INSUFFICIENT_EVIDENCE':'тиімді нұсқа анықталмады'}}
    result=[]
    decisions={
      'en':{'CONDITIONALLY_PROCESSING_PREFERRED':'processing may be preferable under the stated conditions','CONDITIONALLY_SELLING_PREFERRED':'selling may be preferable under the stated conditions','PROCESSING_PREFERRED':'processing is preferred in this comparison','SELLING_PREFERRED':'selling is preferred in this comparison','CHP':'combined heat and electricity','BMP':'laboratory methane-potential test'},
      'kk':{'CONDITIONALLY_PROCESSING_PREFERRED':'берілген шарттарда өңдеу тиімді болуы мүмкін','CONDITIONALLY_SELLING_PREFERRED':'берілген шарттарда сату тиімді болуы мүмкін','PROCESSING_PREFERRED':'осы салыстыруда өңдеу тиімді','SELLING_PREFERRED':'осы салыстыруда сату тиімді','CHP':'жылу мен электр энергиясын бірге өндіру','BMP':'зертханалық метан әлеуетінің сынағы'},
      'ru':{'BMP':'лабораторного потенциала метана'}}
    meanings[language].update(decisions[language])
    for paragraph in paragraphs:
        for key,value in meanings.get(language,meanings['ru']).items():paragraph=paragraph.replace(key,value)
        result.append(paragraph)
    return result

def sections(paragraphs,language):
    titles={'ru':['Краткий ответ','Что получится','Что я рекомендую','Почему'],
            'en':['Short answer','Expected output','Recommendation','Why'],
            'kk':['Қысқаша жауап','Не алуға болады','Ұсынысым','Неліктен']}[language]
    p=list(paragraphs)
    if len(p)<=2:return [{'title':titles[i],'body':x} for i,x in enumerate(p)]
    return [{'title':titles[0],'body':p[0]},{'title':titles[1],'body':p[1]},
            {'title':titles[2],'body':p[2]},{'title':titles[3],'body':' '.join(p[3:])}] if len(p)>3 else [{'title':titles[i],'body':x} for i,x in enumerate(p)]
