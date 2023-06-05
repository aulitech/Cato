
auli_cato_loc=/e/
loc_d=/d/   # dont know shell well enough to do this w full_reprogram :(

echo "Checking connection"
while [ ! -d $auli_cato_loc ]
do
    if [ -d $loc_d ]
    then
        auli_cato_loc=$loc_d
    fi
    
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