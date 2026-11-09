import QtQuick 2.15

Text {
    property var theme
    color: theme.ink
    font.family: theme.bodyFont
    font.pixelSize: theme.hintSize
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter
    wrapMode: Text.Wrap
    elide: Text.ElideRight
}
