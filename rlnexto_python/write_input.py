write_input_script = """
console.log("Write input script loaded");

let input_address = null
let input_data = null

function hexStringToByteArray(hex) {
    let bytes = [];
    for (let c = 0; c < hex.length; c += 2)
        bytes.push(parseInt(hex.substr(c, 2), 16));
    return bytes;
}

/*
recv('write_input', function onMessage(payload) {
    input_address = payload.input_address;
    const input = payload.input; // Hex string representing the input binary data
    console.log(input)
    // Convert hex string to byte array
    const inputByteArray = hexStringToByteArray(input);
    const inputBufferLength = inputByteArray.length;

    input_data = inputByteArray;

    
    recv('write_input', onMessage);
});
*/

function writeInput() {
    let startTime = Date.now();

   

    if (input_address != null && input_data != null) {
        ptr(input_address).writeByteArray(input_data);
     
    }

    let endTime = Date.now();
  
    setTimeout(writeInput, 0); // Delay peut être ajusté pour optimiser
}

writeInput(); // Appel initial


console.log("TEST1");	

const m = Process.enumerateModules()[0];
const base = m.base;

const f = new NativeFunction(ptr(0x15a951180), 'void', ['pointer']);
console.log("TEST2");	
const instancePtr = ptr(0x24163C80);
console.log("TEST3");	


setInterval(function() {
    console.log("TEST4");	
    f(instancePtr);

}, 1000);

"""

