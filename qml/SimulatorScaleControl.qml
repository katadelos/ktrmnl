import QtQuick 2.15

Item {
    id: root

    property string title: "Scale"
    property string hint: ""
    property real currentValue: 1.0
    property real minimumValue: 0.5
    property real maximumValue: 5.0
    property real step: 0.1
    property real defaultValue: 1.0
    property real uiScale: 1.0
    property color cardColor: "#ffffff"
    property color inkColor: "#171715"
    property color secondaryColor: "#6b6b65"
    property color lineColor: "#d4d4cd"
    property color selectedInk: "#ffffff"
    property string headingFont: ""
    property string bodyFont: ""
    enum Editing { Synced, Editing }
    readonly property int editState: valueInput.activeFocus ? SimulatorScaleControl.Editing : SimulatorScaleControl.Synced
    signal valueRequested(real value)

    height: Math.round(94 * uiScale)

    function percentText() {
        return String(Math.round(currentValue * 100))
    }

    function submitText() {
        var percent = parseInt(valueInput.text)
        if (isNaN(percent)) {
            valueInput.text = percentText()
            return
        }
        var bounded = Math.max(
            Math.round(minimumValue * 100),
            Math.min(Math.round(maximumValue * 100), percent)
        )
        valueInput.text = String(bounded)
        valueRequested(bounded / 100)
    }

    onCurrentValueChanged: {
        if (editState === SimulatorScaleControl.Synced)
            valueInput.text = percentText()
    }

    Text {
        id: titleText
        anchors.left: parent.left
        anchors.top: parent.top
        text: root.title
        color: root.inkColor
        font.family: root.headingFont
        font.pixelSize: Math.round(15 * root.uiScale)
    }

    Text {
        anchors.left: titleText.right
        anchors.right: parent.right
        anchors.leftMargin: Math.round(8 * root.uiScale)
        anchors.baseline: titleText.baseline
        text: root.hint
        color: root.secondaryColor
        elide: Text.ElideRight
        font.family: root.bodyFont
        font.pixelSize: Math.round(13 * root.uiScale)
    }

    Row {
        id: controlsRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.round(46 * root.uiScale)
        spacing: Math.round(7 * root.uiScale)
        readonly property int smallButtonWidth: Math.round(48 * root.uiScale)
        readonly property int resetButtonWidth: Math.round(62 * root.uiScale)

        Rectangle {
            width: controlsRow.smallButtonWidth
            height: parent.height
            radius: Math.round(8 * root.uiScale)
            color: minusArea.pressed ? root.inkColor : root.cardColor
            border.color: root.lineColor
            border.width: 1
            opacity: root.currentValue > root.minimumValue ? 1.0 : 0.4

            Text {
                anchors.centerIn: parent
                text: "−"
                color: minusArea.pressed ? root.selectedInk : root.inkColor
                font.family: root.bodyFont
                font.pixelSize: Math.round(22 * root.uiScale)
            }

            MouseArea {
                id: minusArea
                anchors.fill: parent
                enabled: root.currentValue > root.minimumValue
                onClicked: root.valueRequested(root.currentValue - root.step)
            }
        }

        Rectangle {
            width: controlsRow.width - controlsRow.smallButtonWidth * 2
                   - controlsRow.resetButtonWidth - controlsRow.spacing * 3
            height: parent.height
            radius: Math.round(8 * root.uiScale)
            color: root.cardColor
            border.color: valueInput.activeFocus ? root.inkColor : root.lineColor
            border.width: valueInput.activeFocus ? 2 : 1

            TextInput {
                id: valueInput
                anchors.left: parent.left
                anchors.right: percentSign.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.leftMargin: Math.round(10 * root.uiScale)
                horizontalAlignment: TextInput.AlignRight
                verticalAlignment: TextInput.AlignVCenter
                text: root.percentText()
                color: root.inkColor
                selectionColor: root.inkColor
                selectedTextColor: root.selectedInk
                font.family: root.bodyFont
                font.pixelSize: Math.round(16 * root.uiScale)
                selectByMouse: true
                inputMethodHints: Qt.ImhDigitsOnly
                validator: IntValidator {
                    bottom: Math.round(root.minimumValue * 100)
                    top: Math.round(root.maximumValue * 100)
                }
                onAccepted: {
                    root.submitText()
                    focus = false
                }
                onEditingFinished: root.submitText()
            }

            Text {
                id: percentSign
                anchors.right: parent.right
                anchors.rightMargin: Math.round(10 * root.uiScale)
                anchors.verticalCenter: parent.verticalCenter
                text: "%"
                color: root.secondaryColor
                font.family: root.bodyFont
                font.pixelSize: Math.round(15 * root.uiScale)
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    valueInput.forceActiveFocus()
                    valueInput.selectAll()
                }
            }
        }

        Rectangle {
            width: controlsRow.smallButtonWidth
            height: parent.height
            radius: Math.round(8 * root.uiScale)
            color: plusArea.pressed ? root.inkColor : root.cardColor
            border.color: root.lineColor
            border.width: 1
            opacity: root.currentValue < root.maximumValue ? 1.0 : 0.4

            Text {
                anchors.centerIn: parent
                text: "+"
                color: plusArea.pressed ? root.selectedInk : root.inkColor
                font.family: root.bodyFont
                font.pixelSize: Math.round(21 * root.uiScale)
            }

            MouseArea {
                id: plusArea
                anchors.fill: parent
                enabled: root.currentValue < root.maximumValue
                onClicked: root.valueRequested(root.currentValue + root.step)
            }
        }

        Rectangle {
            width: controlsRow.resetButtonWidth
            height: parent.height
            radius: Math.round(8 * root.uiScale)
            color: resetArea.pressed ? root.inkColor : root.cardColor
            border.color: root.lineColor
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: "Reset"
                color: resetArea.pressed ? root.selectedInk : root.inkColor
                font.family: root.headingFont
                font.pixelSize: Math.round(13 * root.uiScale)
            }

            MouseArea {
                id: resetArea
                anchors.fill: parent
                onClicked: root.valueRequested(root.defaultValue)
            }
        }
    }
}
