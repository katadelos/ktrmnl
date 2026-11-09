import QtQuick 2.15

Rectangle {
    id: root
    property var theme
    property bool checked: false
    property bool inverted: false

    width: Math.round(48 * theme.scale)
    height: Math.round(26 * theme.scale)
    radius: Math.round(height / 2)
    color: checked ? (inverted ? theme.selectedInk : theme.ink)
                   : (inverted ? theme.selectedWash : theme.wash)
    border.color: inverted ? theme.selectedOutline : theme.outline
    border.width: theme.controlBorderWidth

    Rectangle {
        width: Math.round(20 * root.theme.scale)
        height: width
        radius: Math.round(width / 2)
        anchors.verticalCenter: parent.verticalCenter
        x: root.checked
           ? parent.width - width - Math.round(3 * root.theme.scale)
           : Math.round(3 * root.theme.scale)
        color: root.checked ? (root.inverted ? root.theme.selectedPaper : root.theme.paper)
                            : (root.inverted ? root.theme.selectedSecondary : root.theme.secondary)
    }
}
