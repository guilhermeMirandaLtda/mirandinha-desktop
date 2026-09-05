"""
Sessão SAP falsa compartilhada pelos testes do Studio — não é um arquivo de teste
(prefixo '_' evita que o pytest tente coletá-lo). Implementa só o que os executores do
GraphTask realmente chamam, então prova a lógica de resolução de alvo e cada handler sem
precisar de pywin32 nem do SAP aberto.
"""


class FakeElement:
    def __init__(self, row_count=0, cells=None):
        self.text = None
        self.selected = None
        self.selectedNode = None
        self.pressed = False
        self.pressed_buttons = []
        self.currentCellRow = None
        self.currentCellColumn = None
        self.double_clicked = False
        self.rowCount = row_count
        self._cells = cells or {}  # (row, col) -> value

    def press(self):
        self.pressed = True

    def pressButton(self, name):
        self.pressed_buttons.append(name)

    def select(self):
        self.pressed = True

    def doubleClickCurrentCell(self):
        self.double_clicked = True

    def GetCellValue(self, row, col):
        if (row, col) not in self._cells:
            raise Exception(f"coluna '{col}' não existe na linha {row}")
        return self._cells[(row, col)]

    def sendVKey(self, code):
        self.pressed_buttons.append(f"vkey:{code}")


class FakeSapGuiSession:
    """Substitui SapSession.session — só implementa findById()."""

    def __init__(self, elements: dict = None):
        self.elements = elements or {}

    def findById(self, element_id):
        if element_id not in self.elements:
            raise Exception(f"elemento não encontrado: {element_id}")
        return self.elements[element_id]

    def register(self, element_id, element):
        self.elements[element_id] = element
        return element
