import QtQuick 2.15

Rectangle {
    id: root
    property var theme
    property bool checked: false
    property bool inverted: false

    width: Math.round(25 * theme.scale)
    height: width
    radius: Math.round(width / 2)
    color: "transparent"
    border.color: inverted ? theme.selectedInk : theme.ink
    border.width: theme.divider

    Rectangle {
        anchors.centerIn: parent
        visible: root.checked
        width: Math.round(root.width * 11 / 25)
        height: width
        radius: Math.round(width / 2)
        color: root.inverted ? root.theme.selectedInk : root.theme.ink
    }
}
