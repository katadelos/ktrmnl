import QtQuick 2.15

Rectangle {
    id: root
    property var theme
    property bool checked: false
    property bool inverted: false

    width: Math.round(48 * theme.scale)
    height: Math.round(26 * theme.scale)
    radius: Math.round(height / 2)
    readonly property color foreground: inverted ? theme.selectedInk : theme.ink
    readonly property color background: inverted ? theme.selectedPaper : theme.paper
    color: checked ? foreground : background
    border.color: foreground
    border.width: theme.controlBorderWidth

    Rectangle {
        width: Math.round(20 * root.theme.scale)
        height: width
        radius: Math.round(width / 2)
        anchors.verticalCenter: parent.verticalCenter
        x: root.checked
           ? parent.width - width - Math.round(3 * root.theme.scale)
           : Math.round(3 * root.theme.scale)
        color: root.checked ? root.background : root.foreground
    }
}
