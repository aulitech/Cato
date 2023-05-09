
auli_cato_loc=/e/

echo "Checking connection"
while [ ! -d $auli_cato_loc ]
do
    sleep 1
    echo "    Waiting for connection"
done

WHITELIST="./scripts/whitelist.txt"
while read -r line
do
    line=${line:0:-1}
    echo "    Copying $line to $auli_cato_loc"
    cp $line $auli_cato_loc
done < "$WHITELIST"