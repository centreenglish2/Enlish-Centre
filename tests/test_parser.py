from pdfgen.parser import parse_questions

def test_parser():
    qs = parse_questions('''1. क्रम क्या है?\nA) पहला\nB) दूसरा\nC) तीसरा\nD) चौथा\n\n2) Hello?\nA. One\nB. Two\nC. Three\nD. Four\n''')
    assert len(qs) == 2
    assert qs[0].text == 'क्रम क्या है?'
    assert qs[0].options[0] == 'पहला'
    assert qs[1].options[3] == 'Four'
