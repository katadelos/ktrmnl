import QtQuick 2.15
import EBoard 1.0 as EBoard

EBoard.Keyboard {
    property var theme
    property var translator
    paper: theme.paper
    ink: theme.ink
    fontFamily: theme.bodyFont
    uiScale: theme.scale
    bodySize: theme.keyboardKeySize
    controlSize: theme.controlSize
    headingSize: theme.keyboardNumberSize
    iconSize: theme.keyboardSymbolSize
    trayBorderWidth: theme.controlBorderWidth
    // Eboard uses a two-pixel outline for the physical-key navigation cursor.
    keyBorderWidth: 1
    touchLanguage: translator ? String(translator.language) : "en"
}
